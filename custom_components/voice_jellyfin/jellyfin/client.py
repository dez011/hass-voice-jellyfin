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

    @staticmethod
    def _check_status(resp: aiohttp.ClientResponse, url: str) -> None:
        """Raise a clean error for non-2xx responses instead of letting
        resp.json() crash on an empty/HTML error body."""
        if resp.status == 401:
            raise PermissionError("Jellyfin API key rejected (401) — check Dashboard → API Keys")
        if resp.status >= 400:
            raise ConnectionError(f"Jellyfin API error {resp.status} for {url}")

    async def _get_json(self, url: str, params: Optional[dict[str, Any]] = None) -> Any:
        session = self._get_session()
        async with session.get(url, params=params, headers=self._h()) as resp:
            self._check_status(resp, url)
            return await resp.json(content_type=None)

    async def _async_effective_user_id(self, user_id: str = "") -> str:
        """Resolve a usable Jellyfin user id.

        Order: explicit argument → configured auth user → first user reported
        by the server (cached). Returns "" if none can be resolved.
        """
        if user_id:
            return user_id
        if self._auth.user_id:
            return self._auth.user_id
        try:
            users = await self._get_json(f"{self._auth.base_url()}/Users")
            if users:
                resolved = users[0].get("Id", "")
                if resolved:
                    self._auth.user_id = resolved
                    _LOGGER.debug("Resolved Jellyfin user id from /Users: %s", resolved)
                return resolved
        except Exception as exc:
            _LOGGER.warning("Could not resolve Jellyfin user id: %s", exc)
        return ""

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

    async def async_get_users(self) -> list[dict[str, str]]:
        """Return every Jellyfin user visible to this API key, for the
        setup-wizard user picker: [{"id": ..., "name": ...}, ...]."""
        data = await self._get_json(f"{self._auth.base_url()}/Users")
        return [
            {"id": u["Id"], "name": u.get("Name", "")}
            for u in (data or [])
            if u.get("Id")
        ]

    async def async_get_libraries(self) -> list[Library]:
        data = await self._get_json(f"{self._auth.base_url()}/Library/VirtualFolders")
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

        The local catalog only indexes Movies and Series, so searches for
        other item types (episodes, music, …) always go to the API, and a
        catalog miss falls back to an API search as a last resort.
        """
        use_catalog = (
            self._catalog is not None
            and self._catalog.size > 0
            and type_filter in (None, "Movie", "Series")
        )
        if use_catalog:
            items = self._catalog.search(query, limit, type_filter=type_filter, genre_hint=genre_hint, year=year)
        else:
            items = await self._api_search(query, limit, type_filter=type_filter)

        filtered = bool(type_filter or genre_hint or year)
        if not items and raw_query and (filtered or raw_query.strip().lower() != query.strip().lower()):
            _LOGGER.debug("Search fallback: retrying unfiltered with raw query %r", raw_query)
            if use_catalog:
                items = self._catalog.search(raw_query, limit)
            else:
                items = await self._api_search(raw_query, limit)

        if not items and use_catalog:
            _LOGGER.debug("Catalog found nothing for %r; falling back to API search", query)
            items = await self._api_search(raw_query or query, limit)
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
        url = f"{self._auth.base_url()}/Items"
        params = {
            "SearchTerm": term,
            "Limit": limit,
            "Recursive": "true",
            "IncludeItemTypes": item_types,
            "Fields": "Genres,ImageTags",
            "EnableImages": "true",
        }
        data = await self._get_json(url, params)
        return data.get("Items", [])

    async def async_build_catalog(self) -> None:
        """Fetch all Movies and Series and build the local search catalog."""
        from .catalog import JellyfinCatalog
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
            data = await self._get_json(url, params)
            page = data.get("Items", [])
            total = data.get("TotalRecordCount", 0)
            all_items.extend(page)
            _LOGGER.debug("Catalog fetch: %d/%d", len(all_items), total)
            # Advance by items actually received — a server may return fewer
            # than page_size per page; trusting page_size would skip items.
            if not page or (total and len(all_items) >= total):
                break
            if len(all_items) >= 100_000:  # runaway guard for servers with broken pagination
                _LOGGER.warning("Catalog fetch aborted at %d items", len(all_items))
                break
            start += len(page)

        media_items = [MediaItem.from_api(i, base) for i in all_items]
        catalog = JellyfinCatalog()
        catalog.build(media_items)
        self._catalog = catalog

    async def async_get_recently_added(self, library_id: Optional[str] = None, limit: int = 20) -> list[MediaItem]:
        url = f"{self._auth.base_url()}/Items/Latest"
        params: dict[str, Any] = {"Limit": limit, "Fields": "Genres,ImageTags", "EnableImages": "true"}
        # /Items/Latest resolves the user from the token; an API key carries no
        # user, so pass an explicit UserId whenever one can be resolved.
        user_id = await self._async_effective_user_id()
        if user_id:
            params["UserId"] = user_id
        if library_id:
            params["ParentId"] = library_id
        data = await self._get_json(url, params)
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
        base = self._auth.base_url()
        user_id = await self._async_effective_user_id(user_id)

        # Season-specific: jump straight to S{n}E1
        if season_number is not None:
            ep_params: dict[str, Any] = {
                "Season": season_number,
                "Limit": 1,
                "SortBy": "SortName",
                "Fields": "UserData",
            }
            if user_id:
                ep_params["UserId"] = user_id
            ep_data = await self._get_json(f"{base}/Shows/{series_id}/Episodes", ep_params)
            items = ep_data.get("Items", [])
            if items:
                ep = items[0]
                ticks = ep.get("UserData", {}).get("PlaybackPositionTicks", 0)
                _LOGGER.debug("Series play target: season %s first ep %r ticks=%s", season_number, ep.get("Name"), ticks)
                return ep["Id"], ticks
            _LOGGER.warning("No episodes found for series %s season %s", series_id, season_number)
            return None

        # 1. In-progress episode (requires a resolved user)
        if user_id:
            resume_data = await self._get_json(
                f"{base}/Users/{user_id}/Items/Resume",
                {"ParentId": series_id, "Limit": 1, "MediaTypes": "Video"},
            )
            resume_items = resume_data.get("Items", [])
            if resume_items:
                ep = resume_items[0]
                ticks = ep.get("UserData", {}).get("PlaybackPositionTicks", 0)
                _LOGGER.debug("Series play target: resuming %r at tick %d", ep.get("Name"), ticks)
                return ep["Id"], ticks

            # 2. NextUp
            nextup_data = await self._get_json(
                f"{base}/Shows/NextUp",
                {"SeriesId": series_id, "UserId": user_id, "Limit": 1, "Fields": "UserData"},
            )
            nextup_items = nextup_data.get("Items", [])
            if nextup_items:
                ep = nextup_items[0]
                _LOGGER.debug("Series play target: next up %r", ep.get("Name"))
                return ep["Id"], 0

        # 3. First episode
        ep1_params: dict[str, Any] = {"Limit": 1, "SortBy": "SortName"}
        if user_id:
            ep1_params["UserId"] = user_id
        ep1_data = await self._get_json(f"{base}/Shows/{series_id}/Episodes", ep1_params)
        ep1_items = ep1_data.get("Items", [])
        if ep1_items:
            ep = ep1_items[0]
            _LOGGER.debug("Series play target: first episode %r", ep.get("Name"))
            return ep["Id"], 0

        return None

    async def async_get_resume_items(self, user_id: str, limit: int = 10) -> list[MediaItem]:
        user_id = await self._async_effective_user_id(user_id)
        if not user_id:
            _LOGGER.warning("No Jellyfin user id available for resume items")
            return []
        url = f"{self._auth.base_url()}/Users/{user_id}/Items/Resume"
        params = {"Limit": limit, "Fields": "Genres,ImageTags", "EnableImages": "true", "MediaTypes": "Video"}
        data = await self._get_json(url, params)
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in data.get("Items", [])]

    async def async_get_favorites(self, user_id: str, limit: int = 50) -> list[MediaItem]:
        user_id = await self._async_effective_user_id(user_id)
        if not user_id:
            _LOGGER.warning("No Jellyfin user id available for favorites")
            return []
        url = f"{self._auth.base_url()}/Users/{user_id}/Items"
        params = {"IsFavorite": "true", "Recursive": "true", "Limit": limit, "Fields": "Genres,ImageTags", "EnableImages": "true"}
        data = await self._get_json(url, params)
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in data.get("Items", [])]

    async def async_get_by_genre(self, genre: str, library_id: Optional[str] = None) -> list[MediaItem]:
        url = f"{self._auth.base_url()}/Items"
        params: dict[str, Any] = {"Genres": genre, "Recursive": "true", "Fields": "Genres,ImageTags", "EnableImages": "true", "SortBy": "Random", "Limit": 50}
        if library_id:
            params["ParentId"] = library_id
        data = await self._get_json(url, params)
        base = self._auth.base_url()
        return [MediaItem.from_api(i, base) for i in data.get("Items", [])]

    # ------------------------------------------------------------------
    # Sessions / playback
    # ------------------------------------------------------------------

    async def async_get_sessions(self) -> list[PlaybackSession]:
        data = await self._get_json(f"{self._auth.base_url()}/Sessions")
        _LOGGER.debug("Jellyfin get_sessions: count=%d", len(data or []))
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
        base = self._auth.base_url()
        if max_bitrate_kbps:
            # The Play endpoint has no bitrate parameter — quality caps go
            # through the SetMaxStreamingBitrate general command instead.
            cmd_url = f"{base}/Sessions/{session_id}/Command"
            payload = {
                "Name": "SetMaxStreamingBitrate",
                "Arguments": {"Bitrate": str(max_bitrate_kbps * 1000)},
            }
            async with session.post(cmd_url, json=payload, headers=self._h()) as resp:
                await resp.read()
        url = f"{base}/Sessions/{session_id}/Playing"
        params: dict[str, Any] = {"playCommand": "PlayNow", "itemIds": item_id}
        if start_ticks:
            params["startPositionTicks"] = start_ticks
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
        user_id = await self._async_effective_user_id(user_id)
        if not user_id:
            raise ConnectionError("No Jellyfin user id available for favorites")
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
        user_id = await self._async_effective_user_id(user_id)
        url = f"{self._auth.base_url()}/Shows/{series_id}/Episodes"
        params: dict[str, Any] = {
            "SortBy": "PremiereDate",
            "SortOrder": "Descending",
            "Limit": 1,
            "Fields": "PremiereDate",
        }
        if user_id:
            params["UserId"] = user_id
        data = await self._get_json(url, params)
        items = data.get("Items", [])
        if items:
            ep = items[0]
            return ep["Id"], ep.get("Name", "")
        return None

    async def async_get_now_playing(self, device_filter: Optional[str] = None) -> Optional[tuple[str, str]]:
        """Return (item_name, description) for what's currently playing, or None."""
        from .session_select import pick_now_playing
        sessions = await self.async_get_sessions()
        active = pick_now_playing(sessions, device_filter=device_filter)
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
        data = await self._get_json(url, {"Fields": "Chapters"})

        chapters = data.get("Chapters", [])
        seek_ticks: Optional[int] = None
        for i, ch in enumerate(chapters):
            # Chapter names can be JSON null — never assume a string
            if "intro" in (ch.get("Name") or "").lower():
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

    async def async_resume(self, user_id: str, device_filter: Optional[str] = None) -> Optional[str]:
        """Resume the first in-progress item on the active session.

        Picks among sessions belonging to *user_id* (or with no known user);
        when *device_filter* matches a device/client within that pool, that
        session is preferred so resume targets the right TV in a multi-TV
        household instead of whichever session Jellyfin lists first.
        """
        items = await self.async_get_resume_items(user_id, limit=1)
        if not items:
            _LOGGER.debug("No resume items found for user %s", user_id)
            return None

        sessions = await self.async_get_sessions()
        pool = [s for s in sessions if s.user_id == user_id or not s.user_id] or sessions
        active = None
        needle = (device_filter or "").strip().lower()
        if needle:
            active = next(
                (s for s in pool if needle in (s.device_name or "").lower() or needle in (s.client or "").lower()),
                None,
            )
        if active is None:
            active = next(iter(pool), None)
        if not active:
            _LOGGER.warning("No active session found for resume")
            return None

        item = items[0]
        await self.async_play(active.id, item.id, start_ticks=item.resume_ticks)
        return item.name
