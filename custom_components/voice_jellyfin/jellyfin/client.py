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
        self._session_owned = False
        self._catalog: Optional[Any] = None  # JellyfinCatalog when built

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

    async def async_search(
        self,
        query: str,
        limit: int = 20,
        type_filter: Optional[str] = None,
        genre_hint: Optional[str] = None,
        year: Optional[int] = None,
        raw_query: Optional[str] = None,
    ) -> list[MediaItem]:
        """Search using local catalog (if built) with API fallback.

        If filters produce zero hits, retry once unfiltered with *raw_query*
        so titles that contain filter keywords ("Family Guy", "TV Patrol")
        still match.
        """
        if self._catalog is not None and self._catalog.size > 0:
            items = self._catalog.search(query, limit, type_filter=type_filter, genre_hint=genre_hint, year=year)
        else:
            items = await self._api_search(query, limit, type_filter=type_filter)

        filtered = bool(type_filter or genre_hint or year)
        if not items and raw_query and (filtered or raw_query.strip().lower() != query.strip().lower()):
            _LOGGER.debug("Search fallback: retrying unfiltered with raw query %r", raw_query)
            if self._catalog is not None and self._catalog.size > 0:
                items = self._catalog.search(raw_query, limit)
            else:
                items = await self._api_search(raw_query, limit)
        return items

    async def _api_search(self, query: str, limit: int, type_filter: Optional[str] = None) -> list[MediaItem]:
        """Multi-pass Jellyfin API search used before catalog is ready."""
        item_types = type_filter or "Movie,Series,Episode,Audio,MusicAlbum"
        stop = frozenset({"the", "a", "an", "of", "and", "in", "on", "at", "to", "is"})
        items = await self._search_term(query, limit, item_types)
        _LOGGER.debug("Jellyfin API search pass1 query=%r type=%s → %d results: %s",
                      query, type_filter, len(items), [i.get("Name") for i in items[:5]])
        if not items:
            words = [w for w in query.lower().split() if w not in stop and len(w) > 2]
            seen: dict[str, Any] = {}
            for word in words:
                for item in await self._search_term(word, limit, item_types):
                    seen.setdefault(item["Id"], item)
            items = list(seen.values())[:limit]
            _LOGGER.debug("Jellyfin API search pass2 words=%r → %d results", words, len(items))
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in items]

    async def _search_term(self, term: str, limit: int, item_types: str = "Movie,Series,Episode,Audio,MusicAlbum") -> list[dict]:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Items"
        params = {
            "SearchTerm": term,
            "Limit": limit,
            "Recursive": "true",
            "IncludeItemTypes": item_types,
            "Fields": "Genres,ImageTags",
            "EnableImages": "true",
        }
        async with session.get(url, params=params, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        return data.get("Items", [])

    async def async_build_catalog(self) -> None:
        """Fetch all Movies and Series and build the local search catalog."""
        from .catalog import JellyfinCatalog
        session = self._get_session()
        base = self._auth.base_url()
        url = f"{base}/Items"
        all_items: list[dict] = []
        page_size = 500
        start = 0

        while True:
            params: dict[str, Any] = {
                "StartIndex": start,
                "Limit": page_size,
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Series",
                "Fields": "Genres",
                "EnableImages": "false",
                "EnableTotalRecordCount": "true",
            }
            async with session.get(url, params=params, headers=self._h()) as resp:
                data = await resp.json(content_type=None)
            page = data.get("Items", [])
            total = data.get("TotalRecordCount", 0)
            all_items.extend(page)
            _LOGGER.debug("Catalog fetch: %d/%d", len(all_items), total)
            if len(all_items) >= total or not page:
                break
            start += page_size

        media_items = [MediaItem.from_api(i, base) for i in all_items]
        catalog = JellyfinCatalog()
        catalog.build(media_items)
        self._catalog = catalog

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

    async def async_get_series_play_target(
        self, series_id: str, user_id: str, season_number: Optional[int] = None
    ) -> Optional[tuple[str, int]]:
        """Return (episode_id, resume_ticks) for the best episode to play next.

        If season_number is given, play the first episode of that season.
        Otherwise:
          1. In-progress episode for this series (resume mid-episode)
          2. NextUp episode (first unwatched after last completed)
          3. First episode of the series (S1E1)
        Returns None if no episodes found.
        """
        session = self._get_session()
        base = self._auth.base_url()

        # Season-specific: jump straight to S{n}E1
        if season_number is not None:
            ep_url = f"{base}/Shows/{series_id}/Episodes"
            async with session.get(ep_url, params={
                "UserId": user_id,
                "Season": season_number,
                "Limit": 1,
                "SortBy": "SortName",
                "Fields": "UserData",
            }, headers=self._h()) as resp:
                ep_data = await resp.json(content_type=None)
            items = ep_data.get("Items", [])
            if items:
                ep = items[0]
                ticks = ep.get("UserData", {}).get("PlaybackPositionTicks", 0)
                _LOGGER.debug("Series play target: season %d first ep %r ticks=%d", season_number, ep.get("Name"), ticks)
                return ep["Id"], ticks
            _LOGGER.warning("No episodes found for series %s season %d", series_id, season_number)
            return None

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
            _LOGGER.debug("Series play target: resuming %r at tick %d", ep.get("Name"), ticks)
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
            _LOGGER.debug("Series play target: next up %r", ep.get("Name"))
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
            _LOGGER.debug("Series play target: first episode %r", ep.get("Name"))
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
        async with session.get(url, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        _LOGGER.debug("Jellyfin get_sessions: status=%s count=%d", resp.status, len(data or []))
        base = self._auth.base_url()
        return [PlaybackSession.from_api(s, base) for s in (data or [])]

    async def async_play(
        self,
        session_id: str,
        item_id: str,
        start_ticks: int = 0,
        max_bitrate_kbps: Optional[int] = None,
    ) -> None:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing"
        params: dict[str, Any] = {"playCommand": "PlayNow", "itemIds": item_id}
        if start_ticks:
            params["startPositionTicks"] = start_ticks
        if max_bitrate_kbps:
            params["MaxStreamingBitrate"] = max_bitrate_kbps * 1000
        async with session.post(url, params=params, headers=self._h()) as resp:
            await resp.read()
        _LOGGER.debug("Play command sent: session=%s item=%s ticks=%d bitrate=%s", session_id, item_id, start_ticks, max_bitrate_kbps)

    async def async_pause(self, session_id: str) -> None:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing/Pause"
        async with session.post(url, headers=self._h()) as resp:
            await resp.read()

    async def async_unpause(self, session_id: str) -> None:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing/Unpause"
        async with session.post(url, headers=self._h()) as resp:
            await resp.read()

    async def async_stop(self, session_id: str) -> None:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing/Stop"
        async with session.post(url, headers=self._h()) as resp:
            await resp.read()

    async def async_next_track(self, session_id: str) -> None:
        """Skip to the next episode/track."""
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing/Next"
        async with session.post(url, headers=self._h()) as resp:
            await resp.read()
        _LOGGER.debug("Next track sent: session=%s", session_id)

    async def async_set_favorite(self, user_id: str, item_id: str, is_favorite: bool = True) -> None:
        """Add or remove an item from the user's favorites."""
        session = self._get_session()
        url = f"{self._auth.base_url()}/Users/{user_id}/FavoriteItems/{item_id}"
        if is_favorite:
            async with session.post(url, headers=self._h()) as resp:
                await resp.read()
        else:
            async with session.delete(url, headers=self._h()) as resp:
                await resp.read()
        _LOGGER.debug("Favorite %s for item %s user %s", "set" if is_favorite else "cleared", item_id, user_id)

    async def async_get_latest_episode(self, series_id: str, user_id: str) -> Optional[tuple[str, str]]:
        """Return (episode_id, episode_name) of the most recently aired episode."""
        http_session = self._get_session()
        url = f"{self._auth.base_url()}/Shows/{series_id}/Episodes"
        async with http_session.get(url, params={
            "UserId": user_id,
            "SortBy": "PremiereDate",
            "SortOrder": "Descending",
            "Limit": 1,
            "Fields": "PremiereDate",
        }, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        items = data.get("Items", [])
        if items:
            ep = items[0]
            return ep["Id"], ep.get("Name", "")
        return None

    async def async_get_now_playing(self) -> Optional[tuple[str, str]]:
        """Return (item_name, description) for what's currently playing, or None."""
        sessions = await self.async_get_sessions()
        active = next((s for s in sessions if s.item and not s.is_paused), None)
        if not active:
            active = next((s for s in sessions if s.item), None)
        if not active or not active.item:
            return None
        item = active.item
        desc = item.name
        # Include episode info if available from the raw session data
        return item.name, desc

    async def async_skip_intro(self, session_id: str) -> bool:
        """Seek past the intro chapter for the current session.

        Tries to find a chapter named 'intro' first; falls back to seeking
        90 seconds forward if no chapter marker is found.
        Returns True if the seek was performed.
        """
        sessions = await self.async_get_sessions()
        target = next((s for s in sessions if s.id == session_id), None)
        if not target or not target.item:
            return False

        # Fetch item details including chapters
        http_session = self._get_session()
        url = f"{self._auth.base_url()}/Items/{target.item.id}"
        async with http_session.get(url, params={"Fields": "Chapters"}, headers=self._h()) as resp:
            data = await resp.json(content_type=None)

        chapters = data.get("Chapters", [])
        seek_ticks: Optional[int] = None
        for i, ch in enumerate(chapters):
            if "intro" in ch.get("Name", "").lower():
                # Seek to start of next chapter after intro
                if i + 1 < len(chapters):
                    seek_ticks = chapters[i + 1]["StartPositionTicks"]
                break

        if seek_ticks is None:
            # Fallback: jump 90s forward from current position
            _NINETY_SECONDS_TICKS = 90 * 10_000_000
            seek_ticks = target.position_ticks + _NINETY_SECONDS_TICKS

        seek_url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing/Seek"
        async with http_session.post(seek_url, params={"seekPositionTicks": seek_ticks}, headers=self._h()) as resp:
            await resp.read()
        _LOGGER.debug("Skip intro: session=%s seek_ticks=%d", session_id, seek_ticks)
        return True

    async def async_get_sessions_with_item(self) -> list[Any]:
        """Return sessions that have an active NowPlayingItem."""
        sessions = await self.async_get_sessions()
        return [s for s in sessions if s.item]

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
        await self.async_play(active.id, item.id, start_ticks=item.resume_ticks)
        return item.name
