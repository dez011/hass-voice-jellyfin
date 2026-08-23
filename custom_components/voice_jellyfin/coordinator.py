"""DataUpdateCoordinator and shared runtime state for Voice Jellyfin."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    LOGGER_NAME,
    UPDATE_INTERVAL,
    CONF_JELLYFIN_URL,
    CONF_JELLYFIN_API_KEY,
    CONF_JELLYFIN_DEFAULT_USER,
    CONF_JELLYFIN_TARGET_DEVICE,
    CONF_JELLYFIN_VERIFY_SSL,
    CONF_AI_ENABLED,
    CONF_AI_PROVIDER,
    CONF_TV_TYPE,
    CONF_ANDROID_TV_ENTITY,
    CONF_APPLE_TV_ENTITY,
    CONF_ADB_HOST,
    CONF_ADB_PORT,
    TV_TYPE_APPLE,
    TV_TYPE_ANDROID,
    CONF_NAV_WAKE_PHRASE,
    DEFAULT_NAV_WAKE_PHRASE,
    CONF_NAV_CONFIRMATION_SPEECH,
    CONF_CATALOG_REINDEX_INTERVAL,
    DEFAULT_CATALOG_REINDEX_INTERVAL,
    CONF_PREFERRED_CLIENT_PACKAGE,
    DEFAULT_PREFERRED_CLIENT_PACKAGE,
    BITRATE_PRESETS_KBPS,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class VoiceJellyfinCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages all runtime state: Jellyfin connection, AI provider, nav mode."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.entry = entry
        self.jellyfin_client: Any = None
        self.ai_provider: Any = None
        self.tv_controller: Any = None
        self.navigation_mode: Any = None
        self._connected = False
        self._last_command: str = ""
        self._last_media: str = ""
        self._current_provider_label: str = ""
        self._current_device: str = ""
        self._reindex_unsub: Optional[Any] = None
        self._bitrate_idx: int = -1  # -1 = auto; tracks quality step across commands
        self.button_trigger: Any = None
        self._catalog_task: Any = None
        # Substring matched against a Jellyfin session's DeviceName/Client so
        # this entry's commands target its own TV, not just whichever
        # session Jellyfin lists first. Blank = single-TV behavior.
        self._target_device: str = ""

    async def async_setup(self) -> None:
        """Initialize all sub-components."""
        from .jellyfin.client import JellyfinClient
        from .jellyfin.auth import JellyfinAuth
        from .ai.context import AIContext
        from .navigation.mode import NavigationMode
        from .navigation.trigger import ButtonTrigger

        config = {**self.entry.data, **(self.entry.options or {})}

        # Jellyfin — the configured default user scopes resume/favorites calls
        auth = JellyfinAuth(
            url=config[CONF_JELLYFIN_URL],
            api_key=config.get(CONF_JELLYFIN_API_KEY, ""),
            user_id=config.get(CONF_JELLYFIN_DEFAULT_USER) or None,
        )
        self.jellyfin_client = JellyfinClient(auth, verify_ssl=config.get(CONF_JELLYFIN_VERIFY_SSL, True), hass=self.hass)
        self._target_device = str(config.get(CONF_JELLYFIN_TARGET_DEVICE) or "")
        try:
            await self.jellyfin_client.async_connect()
            self._connected = True
        except Exception as err:
            _LOGGER.warning("Jellyfin connection failed at setup: %s", err)

        # AI provider
        self.ai_context = AIContext()
        await self._async_load_ai_provider(config)
        self._current_provider_label = config.get(CONF_AI_PROVIDER, "")

        # TV controller — pick the right backend based on configured type
        tv_type = config.get(CONF_TV_TYPE, TV_TYPE_ANDROID)
        if tv_type == TV_TYPE_APPLE:
            apple_entity = config.get(CONF_APPLE_TV_ENTITY)
            if apple_entity:
                from .tv.apple_tv import AppleTVController
                self.tv_controller = AppleTVController(self.hass, apple_entity)
                self._current_device = apple_entity
        else:
            tv_entity = config.get(CONF_ANDROID_TV_ENTITY)
            adb_host = config.get(CONF_ADB_HOST)
            if tv_entity:
                from .tv.android_tv import AndroidTVController
                self.tv_controller = AndroidTVController(self.hass, tv_entity)
                self._current_device = tv_entity
            elif adb_host:
                # No media_player entity — drive the device over raw TCP ADB
                from .tv.adb import ADBTVController
                adb_port = config.get(CONF_ADB_PORT) or 5555
                self.tv_controller = ADBTVController(adb_host, adb_port)
                self._current_device = f"adb://{adb_host}:{adb_port}"

        # Navigation mode
        self.navigation_mode = NavigationMode(self.hass, self.entry, self)

        # Physical button trigger
        button_entity = config.get("button_entity")
        if button_entity:
            self.button_trigger = ButtonTrigger(self.hass, button_entity, self)
            await self.button_trigger.async_attach()

        # Catalog — build in the background (a large library can take a
        # while and must not block HA startup), then schedule re-indexing
        self._catalog_task = self.hass.async_create_background_task(
            self.async_reindex_catalog(), name="voice_jellyfin_catalog_index"
        )
        self._schedule_reindex(config)

        await self.async_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest status from Jellyfin."""
        try:
            if self.jellyfin_client:
                from .jellyfin.session_select import pick_now_playing, pick_session
                sessions = await self.jellyfin_client.async_get_sessions()
                self._connected = True
                configured_uid = self.jellyfin_client._auth.user_id or None

                now = pick_now_playing(sessions, device_filter=self._target_device)
                now_playing = None
                if now and now.item:
                    now_playing = {
                        "title": now.item.name,
                        "client": now.client or None,
                        "device": now.device_name or None,
                        "user": now.user_name or None,
                        "paused": now.is_paused,
                    }

                # Find the session that would be targeted by the next command.
                # require_item=False so it shows even when nothing is playing.
                user_session = pick_session(
                    sessions, device_filter=self._target_device,
                    require_item=False, user_id=configured_uid,
                )
                active_user = user_session.user_name if user_session else None
                active_session = (
                    f"{user_session.device_name} — {user_session.client}"
                    if user_session else None
                )
                remote_controllable = (
                    user_session.supports_remote_control if user_session else False
                )

                # Real user sessions for the "Sessions" sensor
                real_sessions = [
                    {
                        "id": s.id,
                        "user": s.user_name or "—",
                        "device": s.device_name,
                        "client": s.client,
                        "now_playing": s.item.name if s.item else None,
                        "paused": s.is_paused if s.item else None,
                        "remote_control": s.supports_remote_control,
                    }
                    for s in sessions
                    if s.user_id and s.user_id.replace("0", "")
                ]

                return {
                    "connected": True,
                    "sessions": sessions,
                    "real_sessions": real_sessions,
                    "now_playing": now_playing,
                    "active_user": active_user,
                    "active_session": active_session,
                    "remote_controllable": remote_controllable,
                    "navigation_active": self.navigation_mode.is_active if self.navigation_mode else False,
                    "last_command": self._last_command,
                    "last_media": self._last_media,
                    "current_provider": self._current_provider_label,
                    "current_device": self._current_device,
                }
        except Exception as err:
            self._connected = False
            raise UpdateFailed(f"Jellyfin unreachable: {err}") from err
        return {}

    async def async_reindex_catalog(self) -> None:
        """Fetch all Movies and Series from Jellyfin and rebuild the local search catalog."""
        if not self.jellyfin_client:
            return
        try:
            _LOGGER.info("Starting Jellyfin catalog re-index...")
            await self.jellyfin_client.async_build_catalog()
            _LOGGER.info("Jellyfin catalog re-index complete.")
        except Exception as err:
            _LOGGER.error("Catalog re-index failed: %s", err)

    def _schedule_reindex(self, config: dict[str, Any]) -> None:
        """Set up a periodic catalog re-index timer (cancels any existing one)."""
        from homeassistant.helpers.event import async_track_time_interval
        if self._reindex_unsub:
            self._reindex_unsub()
            self._reindex_unsub = None
        interval_hours = config.get(CONF_CATALOG_REINDEX_INTERVAL, DEFAULT_CATALOG_REINDEX_INTERVAL)
        if interval_hours and interval_hours > 0:
            async def _reindex(_now: Any) -> None:
                await self.async_reindex_catalog()
            self._reindex_unsub = async_track_time_interval(
                self.hass, _reindex, timedelta(hours=interval_hours)
            )
            _LOGGER.info("Catalog re-index scheduled every %d hour(s)", interval_hours)

    async def _async_load_ai_provider(self, config: dict[str, Any]) -> None:
        """Instantiate the configured AI provider."""
        from .ai.providers import build_provider
        self.ai_provider = await build_provider(self.hass, config)

    # Phrases that exit Navigation Mode by voice
    _NAV_OFF_PHRASES = frozenset({
        "exit navigation mode", "navigation mode off", "exit navigation",
        "stop navigation", "stop navigating", "leave navigation mode",
    })

    async def async_handle_voice(self, text: str) -> str:
        """Entry point for raw voice/STT text (Assist, sentence triggers,
        the voice_command service).

        Routing order:
          1. Nav wake phrase        → activate Navigation Mode
          2. Nav off phrase         → deactivate Navigation Mode
          3. Nav mode / hot mic on  → NavigationMode.async_handle_command
          4. Everything else        → the full media command pipeline
        """
        from .navigation.mode import _normalize_phrase

        merged = {**self.entry.data, **(self.entry.options or {})}
        nav = self.navigation_mode
        normalized = _normalize_phrase(text)

        if nav:
            confirm = merged.get(CONF_NAV_CONFIRMATION_SPEECH, True)
            wake = str(merged.get(CONF_NAV_WAKE_PHRASE) or DEFAULT_NAV_WAKE_PHRASE)
            if normalized == _normalize_phrase(wake):
                await nav.async_activate()
                self._last_command = text
                return "Navigation mode on." if confirm else ""
            if normalized in self._NAV_OFF_PHRASES:
                if nav.is_active:
                    await nav.async_deactivate()
                    self._last_command = text
                    return "Navigation mode off." if confirm else ""
            if nav.is_active or nav.hot_mic_active:
                self._last_command = text
                handled = await nav.async_handle_command(text)
                if handled:
                    return ""
        return await self.async_send_command(text)

    async def async_send_command(self, text: str, suppress_error_speech: bool = False) -> str:
        """Route a natural language command through AI and execute it."""
        from .ai.intent_router import IntentRouter
        self._last_command = text
        merged_config = {**self.entry.data, **(self.entry.options or {})}
        ai_enabled = merged_config.get(CONF_AI_ENABLED, False)

        # Check for hot mic toggle phrase before routing (strip punctuation for robustness)
        if self.navigation_mode:
            phrase = self.navigation_mode._get_hot_mic_phrase()
            normalized = "".join(c for c in text.lower() if c.isalnum() or c.isspace()).strip()
            phrase_normalized = "".join(c for c in phrase if c.isalnum() or c.isspace()).strip()
            if normalized == phrase_normalized:
                await self.navigation_mode.async_toggle_hot_mic()
                state = "activated" if self.navigation_mode.hot_mic_active else "deactivated"
                return f"Hot mic {state}."
        preferred_pkg = merged_config.get(CONF_PREFERRED_CLIENT_PACKAGE, DEFAULT_PREFERRED_CLIENT_PACKAGE)
        router = IntentRouter(
            jellyfin=self.jellyfin_client,
            tv=self.tv_controller,
            nav=self.navigation_mode,
            hass=self.hass,
            tv_type=merged_config.get(CONF_TV_TYPE, ""),
            preferred_client_package=preferred_pkg,
            bitrate_presets=BITRATE_PRESETS_KBPS,
            current_bitrate_idx=self._bitrate_idx,
            device_filter=self._target_device,
            # Same value already used to scope resume/favorites auth (line
            # ~87) — reused here so general commands (play/pause/next/etc.)
            # also target that person's session instead of whichever session
            # the Jellyfin API happens to list first.
            user_filter=merged_config.get(CONF_JELLYFIN_DEFAULT_USER) or None,
        )
        result = await router.async_route(text, self.ai_provider, self.ai_context, ai_enabled=ai_enabled)
        if result.media_title:
            self._last_media = result.media_title
        # Persist quality step so next QUALITY_UP/DOWN continues from same point
        self._bitrate_idx = router._bitrate_idx
        try:
            self.async_set_updated_data(await self._async_update_data())
        except Exception:
            _LOGGER.debug("Post-command status refresh failed", exc_info=True)

        reply = result.speech_reply or "Done."
        # In hot mic mode, suppress generic error/fallback speech so silence = ignored
        if suppress_error_speech and reply in (
            "Sorry, I had trouble understanding that.",
            "Sorry, that didn't work.",
            "Done.",
        ):
            return ""
        return reply

    async def async_shutdown(self) -> None:
        """Clean up connections, listeners, and background work."""
        if self._reindex_unsub:
            self._reindex_unsub()
            self._reindex_unsub = None
        if self._catalog_task is not None:
            self._catalog_task.cancel()
            self._catalog_task = None
        if self.button_trigger:
            self.button_trigger.async_detach()
            self.button_trigger = None
        if self.navigation_mode:
            await self.navigation_mode.async_deactivate()
        if self.jellyfin_client:
            await self.jellyfin_client.async_close()
