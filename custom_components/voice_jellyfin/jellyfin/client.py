"""Async Jellyfin HTTP client."""
from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession

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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            if self._hass is not None:
                self._session = async_create_clientsession(
                    self._hass,
                    verify_ssl=self._verify_ssl,
                )
            else:
                connector = aiohttp.TCPConnector(ssl=None if self._verify_ssl else False)
                self._session = aiohttp.ClientSession(connector=connector)
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
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

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

    async def async_search(self, query: str, limit: int = 20) -> list[MediaItem]:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Items"
        params = {
            "SearchTerm": query,
            "Limit": limit,
            "Recursive": "true",
            "IncludeItemTypes": "Movie,Series,Episode,Audio,MusicAlbum",
            "Fields": "Genres,ImageTags",
            "EnableImages": "true",
        }
        async with session.get(url, params=params, headers=self._h()) as resp:
            data = await resp.json(content_type=None)
        items = data.get("Items", [])
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in items]

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
        base = self._auth.base_url()
        return [PlaybackSession.from_api(s, base) for s in (data or [])]

    async def async_play(self, session_id: str, item_id: str) -> None:
        session = self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing"
        params = {"playCommand": "PlayNow", "itemIds": item_id}
        async with session.post(url, params=params, headers=self._h()) as resp:
            await resp.read()
        _LOGGER.debug("Play command sent: session=%s item=%s", session_id, item_id)

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
