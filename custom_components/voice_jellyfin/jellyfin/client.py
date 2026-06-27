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

    def __init__(self, auth: JellyfinAuth) -> None:
        self._auth = auth
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._auth.auth_headers(),
                raise_for_status=True,
            )
        return self._session

    async def async_connect(self) -> dict[str, Any]:
        """GET /health then /System/Info — raises on failure with detail."""
        base = self._auth.base_url()
        session = await self._get_session()

        # Health check first so we get a clear error if the server is unreachable
        health_url = f"{base}/health"
        _LOGGER.info("Checking Jellyfin health at %s", health_url)
        try:
            async with session.get(health_url, raise_for_status=False) as resp:
                _LOGGER.info("Jellyfin /health → HTTP %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Jellyfin /health failed: %s", exc)
            raise

        url = f"{base}/System/Info"
        _LOGGER.info("Connecting to Jellyfin at %s", url)
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                data: dict[str, Any] = await resp.json()
        except Exception as exc:
            _LOGGER.error("Jellyfin /System/Info failed: %s", exc)
            raise

        _LOGGER.info("Connected to Jellyfin %s", data.get("Version", "?"))
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
        """GET /Library/VirtualFolders → list of Library objects."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Library/VirtualFolders"
        async with session.get(url) as resp:
            data = await resp.json()
        return [Library.from_api(item) for item in (data or [])]

    # ------------------------------------------------------------------
    # Search / browse
    # ------------------------------------------------------------------

    async def async_search(
        self, query: str, limit: int = 20
    ) -> list[MediaItem]:
        """Search items by name (fuzzy-ish via Jellyfin's search API)."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Items"
        params = {
            "SearchTerm": query,
            "Limit": limit,
            "Recursive": "true",
            "IncludeItemTypes": "Movie,Series,Episode,Audio,MusicAlbum",
            "Fields": "Genres,ImageTags",
            "EnableImages": "true",
        }
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        items = data.get("Items", [])
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in items]

    async def async_get_recently_added(
        self, library_id: Optional[str] = None, limit: int = 20
    ) -> list[MediaItem]:
        """Return recently-added media items."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Items/Latest"
        params: dict[str, Any] = {
            "Limit": limit,
            "Fields": "Genres,ImageTags",
            "EnableImages": "true",
        }
        if library_id:
            params["ParentId"] = library_id
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in (data or [])]

    async def async_get_resume_items(
        self, user_id: str, limit: int = 10
    ) -> list[MediaItem]:
        """GET /Users/{user_id}/Items/Resume — in-progress items."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Users/{user_id}/Items/Resume"
        params = {
            "Limit": limit,
            "Fields": "Genres,ImageTags",
            "EnableImages": "true",
            "MediaTypes": "Video",
        }
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in data.get("Items", [])]

    async def async_get_favorites(
        self, user_id: str, limit: int = 50
    ) -> list[MediaItem]:
        """Return items marked as favourite by the user."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Users/{user_id}/Items"
        params = {
            "IsFavorite": "true",
            "Recursive": "true",
            "Limit": limit,
            "Fields": "Genres,ImageTags",
            "EnableImages": "true",
        }
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in data.get("Items", [])]

    async def async_get_by_genre(
        self, genre: str, library_id: Optional[str] = None
    ) -> list[MediaItem]:
        """Return items matching a genre, optionally scoped to a library."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Items"
        params: dict[str, Any] = {
            "Genres": genre,
            "Recursive": "true",
            "Fields": "Genres,ImageTags",
            "EnableImages": "true",
            "SortBy": "Random",
            "Limit": 50,
        }
        if library_id:
            params["ParentId"] = library_id
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in data.get("Items", [])]

    # ------------------------------------------------------------------
    # Sessions / playback
    # ------------------------------------------------------------------

    async def async_get_sessions(self) -> list[PlaybackSession]:
        """GET /Sessions → list of active playback sessions."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Sessions"
        async with session.get(url) as resp:
            data = await resp.json()
        base = self._auth.base_url()
        return [PlaybackSession.from_api(s, base) for s in (data or [])]

    async def async_play(self, session_id: str, item_id: str) -> None:
        """POST /Sessions/{session_id}/Playing — start playback of an item."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing"
        params = {
            "playCommand": "PlayNow",
            "itemIds": item_id,
        }
        async with session.post(url, params=params) as resp:
            await resp.read()
        _LOGGER.debug("Play command sent: session=%s item=%s", session_id, item_id)

    async def async_pause(self, session_id: str) -> None:
        """POST /Sessions/{session_id}/Playing/Unpause — toggle pause."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing/Unpause"
        async with session.post(url) as resp:
            await resp.read()

    async def async_stop(self, session_id: str) -> None:
        """DELETE /Sessions/{session_id}/Playing — stop playback."""
        session = await self._get_session()
        url = f"{self._auth.base_url()}/Sessions/{session_id}/Playing"
        async with session.delete(url) as resp:
            await resp.read()

    async def async_resume(self, user_id: str) -> Optional[str]:
        """Resume the first in-progress item on the active session.

        Returns the item name if playback was started, else None.
        """
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
