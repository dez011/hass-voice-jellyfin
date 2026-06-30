"""Async Jellyfin HTTP client."""
from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

from .auth import JellyfinAuth
from .models import Library, MediaItem, PlaybackSession

_LOGGER = logging.getLogger(__name__)


class JellyfinClient:
    """Thin async wrapper around the Jellyfin REST API."""

    def __init__(self, auth: JellyfinAuth, verify_ssl: bool = True, hass: Any = None) -> None:
        self._auth = auth
        self._verify_ssl = verify_ssl
        self._hass = hass
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_owned = False  # True only for sessions we create ourselves

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            if self._hass is not None:
                from homeassistant.helpers.aiohttp_client import async_create_clientsession
                self._session = async_create_clientsession(self._hass, verify_ssl=self._verify_ssl)
                self._session_owned = False
            else:
                connector = aiohttp.TCPConnector(ssl=None if self._verify_ssl else False)
                self._session = aiohttp.ClientSession(connector=connector)
                self._session_owned = True
        return self._session

    def _h(self) -> dict[str, str]:
        """Auth headers passed per-request."""
        return self._auth.auth_headers()

    async def async_connect(self) -> dict[str, Any]:
        """Verify server reachability AND API key validity."""
        base = self._auth.base_url()
        session = self._get_session()

        # 1. Server reachable? (no auth needed)
        pub_url = f"{base}/System/Info/Public"
        try:
            async with session.get(pub_url, raise_for_status=False) as resp:
                if resp.status >= 500:
                    raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
                data: dict[str, Any] = await resp.json(content_type=None)
        except Exception as exc:
            _LOGGER.error("Jellyfin /System/Info/Public failed: %s", exc)
            raise ConnectionError(f"Cannot reach Jellyfin at {base}: {exc}") from exc

        # 2. API key valid? (auth required)
        sessions_url = f"{base}/Sessions"
        try:
            async with session.get(sessions_url, headers=self._h(), raise_for_status=False) as resp:
                if resp.status == 401:
                    raise PermissionError("API key is invalid or missing — check Jellyfin Dashboard → API Keys")
                if resp.status >= 400:
                    raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
        except PermissionError:
            raise
        except Exception as exc:
            _LOGGER.error("Jellyfin /Sessions failed: %s", exc)
            raise

        _LOGGER.info("Connected to Jellyfin %s (auth OK)", data.get("Version", "?"))
        return data

    async def async_close(self) -> None:
        """Close the underlying aiohttp session (only if we own it)."""
        if self._session_owned and self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._session_owned = False

    # ------------------------------------------------------------------
    # Library
    # ------------------------------------------------------------------

    async def async_get_libraries(self) -> list[Library]:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Library/VirtualFolders"
        async with session.get(url, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        return [Library.from_api(item) for item in (data or [])]

    # ------------------------------------------------------------------
    # Search / browse
    # ------------------------------------------------------------------

    # Words too generic to search on their own
    _STOP_WORDS = frozenset({"the", "a", "an", "of", "and", "in", "on", "at", "to", "is"})

    async def async_search(self, query: str, limit: int = 20) -> list[MediaItem]:
        """Search Jellyfin with multi-pass fallback.

        Pass 1: full query as-is.
        Pass 2 (if 0 results): each significant word individually, merged & deduplicated.
        """
        items = await self._search_term(query, limit)
        _LOGGER.warning(
            "Jellyfin search pass1 query=%r → %d results: %s",
            query, len(items), [i.get("Name") for i in items[:5]],
        )

        if not items:
            words = [w for w in query.lower().split() if w not in self._STOP_WORDS and len(w) > 2]
            seen: dict[str, Any] = {}
            for word in words:
                word_items = await self._search_term(word, limit)
                _LOGGER.warning(
                    "Jellyfin search pass2 word=%r → %d results: %s",
                    word, len(word_items), [i.get("Name") for i in word_items[:5]],
                )
                for item in word_items:
                    seen.setdefault(item["Id"], item)
            items = list(seen.values())[:limit]

        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in items]

    async def _search_term(self, term: str, limit: int) -> list[dict]:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Items"
        params = {
            "SearchTerm": term,
            "Limit": limit,
            "Recursive": "true",
            "IncludeItemTypes": "Movie,Series,Episode,Audio,MusicAlbum",
            "Fields": "Genres,ImageTags",
            "EnableImages": "true",
        }
        async with session.get(url, params=params, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        return data.get("Items", [])

    async def async_get_recently_added(self, library_id: Optional[str] = None, limit: int = 20) -> list[MediaItem]:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Items/Latest"
        params: dict[str, Any] = {"Limit": limit, "Fields": "Genres,ImageTags", "EnableImages": "true"}
        if library_id:
            params["ParentId"] = library_id
        async with session.get(url, params=params, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in (data or [])]

    async def async_get_series_play_target(self, series_id: str, user_id: str) -> Optional[tuple[str, int]]:
        """Return (episode_id, resume_ticks) for the best episode to play next.

        Priority:
          1. In-progress episode for this series (resume mid-episode)
          2. NextUp episode (first unwatched after last completed)
          3. First episode of the series (S1E1)
        Returns None if no episodes found.
        """
        session = self._get_session()
        base = self._auth.base_url()

        # 1. In-progress episode
        resume_url = f"{base}/Users/{user_id}/Items/Resume"
        async with session.get(resume_url, params={
            "ParentId": series_id, "Limit": 1, "MediaTypes": "Video",
        }, headers=self._h()) as resp:
            resume_data = await resp.json(content_type=None)
        resume_items = resume_data.get("Items", [])
        if resume_items:
            ep = resume_items[0]
            ticks = ep.get("UserData", {}).get("PlaybackPositionTicks", 0)
            _LOGGER.warning("Series play target: resuming %r at tick %d", ep.get("Name"), ticks)
            return ep["Id"], ticks

        # 2. NextUp
        nextup_url = f"{base}/Shows/NextUp"
        async with session.get(nextup_url, params={
            "SeriesId": series_id, "UserId": user_id, "Limit": 1,
            "Fields": "UserData",
        }, headers=self._h()) as resp:
            nextup_data = await resp.json(content_type=None)
        nextup_items = nextup_data.get("Items", [])
        if nextup_items:
            ep = nextup_items[0]
            _LOGGER.warning("Series play target: next up %r", ep.get("Name"))
            return ep["Id"], 0

        # 3. First episode
        ep1_url = f"{base}/Shows/{series_id}/Episodes"
        async with session.get(ep1_url, params={
            "UserId": user_id, "Limit": 1, "SortBy": "SortName",
        }, headers=self._h()) as resp:
            ep1_data = await resp.json(content_type=None)
        ep1_items = ep1_data.get("Items", [])
        if ep1_items:
            ep = ep1_items[0]
            _LOGGER.warning("Series play target: first episode %r", ep.get("Name"))
            return ep["Id"], 0

        return None

    async def async_get_resume_items(self, user_id: str, limit: int = 10) -> list[MediaItem]:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Users/{user_id}/Items/Resume"
        params = {"Limit": limit, "Fields": "Genres,ImageTags", "EnableImages": "true", "MediaTypes": "Video"}
        async with session.get(url, params=params, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in data.get("Items", [])]

    async def async_get_favorites(self, user_id: str, limit: int = 50) -> list[MediaItem]:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Users/{user_id}/Items"
        params = {"IsFavorite": "true", "Recursive": "true", "Limit": limit, "Fields": "Genres,ImageTags", "EnableImages": "true"}
        async with session.get(url, params=params, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in data.get("Items", [])]

    async def async_get_by_genre(self, genre: str, library_id: Optional[str] = None) -> list[MediaItem]:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Items"
        params: dict[str, Any] = {"Genres": genre, "Recursive": "true", "Fields": "Genres,ImageTags", "EnableImages": "true", "SortBy": "Random", "Limit": 50}
        if library_id:
            params["ParentId"] = library_id
        async with session.get(url, params=params, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in data.get("Items", [])]

    # ------------------------------------------------------------------
    # Sessions / playback
    # ------------------------------------------------------------------

    async def async_get_sessions(self) -> list[PlaybackSession]:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions"
        _LOGGER.warning("Jellyfin get_sessions request: url=%s", url)
        async with session.get(url, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        _LOGGER.warning("Jellyfin get_sessions response: status=%s count=%d", resp.status, len(data or []))
        base = self._auth.base_url()
        return [PlaybackSession.from_api(s, base) for s in (data or [])]

    async def async_play(self, session_id: str, item_id: str, start_ticks: int = 0) -> None:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing"
        params: dict[str, Any] = {"playCommand": "PlayNow", "itemIds": item_id}
        if start_ticks:
            params["startPositionTicks"] = start_ticks
        async with session.post(url, params=params, headers=self._h()) as resp:
            await resp.read()
        _LOGGER.debug("Play command sent: session=%s item=%s ticks=%d", session_id, item_id, start_ticks)

    async def async_pause(self, session_id: str) -> None:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing/Unpause"
        async with session.post(url, headers=self._h()) as resp:
            await resp.read()

    async def async_stop(self, session_id: str) -> None:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing"
        async with session.delete(url, headers=self._h()) as resp:
            await resp.read()

    async def async_resume(self, user_id: str) -> Optional[str]:
        """Resume the first in-progress item on the active session."""
        items = await self.async_get_resume_items(user_id, limit=1)
        if not items:
            _LOGGER.debug("No resume items found for user %s", user_id)
            return None

        sessions = await self.async_get_sessions()
        active = next(
            (s for s in sessions if s.user_id == user_id or not s.user_id),
            next(iter(sessions), None),
        )
        if not active:
            _LOGGER.warning("No active session found for resume")
            return None

        item = items[0]
        await self.async_play(active.id, item.id)
        return item.name
