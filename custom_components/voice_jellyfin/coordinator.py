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
    CONF_JELLYFIN_VERIFY_SSL,
    CONF_AI_ENABLED,
    CONF_AI_PROVIDER,
    CONF_TV_TYPE,
    CONF_ANDROID_TV_ENTITY,
    CONF_APPLE_TV_ENTITY,
    TV_TYPE_APPLE,
    TV_TYPE_ANDROID,
    CONF_CATALOG_REINDEX_INTERVAL,
    DEFAULT_CATALOG_REINDEX_INTERVAL,
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

    async def async_setup(self) -> None:
        """Initialize all sub-components."""
        from .jellyfin.client import JellyfinClient
        from .jellyfin.auth import JellyfinAuth
        from .ai.context import AIContext
        from .navigation.mode import NavigationMode
        from .navigation.trigger import ButtonTrigger

        config = {**self.entry.data, **(self.entry.options or {})}

        # Jellyfin
        auth = JellyfinAuth(
            url=config[CONF_JELLYFIN_URL],
            api_key=config.get(CONF_JELLYFIN_API_KEY, ""),
        )
        self.jellyfin_client = JellyfinClient(auth, verify_ssl=config.get(CONF_JELLYFIN_VERIFY_SSL, True), hass=self.hass)
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
            if tv_entity:
                from .tv.android_tv import AndroidTVController
                self.tv_controller = AndroidTVController(self.hass, tv_entity)
                self._current_device = tv_entity

        # Navigation mode
        self.navigation_mode = NavigationMode(self.hass, self.entry, self)

        # Physical button trigger
        button_entity = config.get("button_entity")
        if button_entity:
            self.button_trigger = ButtonTrigger(self.hass, button_entity, self)
            await self.button_trigger.async_attach()

        # Catalog — build in the background (a large library can take a
        # while and must not block HA startup), then schedule re-indexing
        self.hass.async_create_background_task(
            self.async_reindex_catalog(), name="voice_jellyfin_catalog_index"
        )
        self._schedule_reindex(config)

        await self.async_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest status from Jellyfin."""
        try:
            if self.jellyfin_client:
                sessions = await self.jellyfin_client.async_get_sessions()
                self._connected = True
                return {
                    "connected": True,
                    "sessions": sessions,
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

    async def async_send_command(self, text: str) -> str:
        """Route a natural language command through AI and execute it."""
        from .ai.intent_router import IntentRouter
        self._last_command = text
        merged_config = {**self.entry.data, **(self.entry.options or {})}
        ai_enabled = merged_config.get(CONF_AI_ENABLED, False)
        router = IntentRouter(
            jellyfin=self.jellyfin_client,
            tv=self.tv_controller,
            nav=self.navigation_mode,
            hass=self.hass,
            tv_type=self.entry.data.get(CONF_TV_TYPE, ""),
        )
        result = await router.async_route(text, self.ai_provider, self.ai_context, ai_enabled=ai_enabled)
        if result.media_title:
            self._last_media = result.media_title
        try:
            self.async_set_updated_data(await self._async_update_data())
        except Exception:
            _LOGGER.debug("Post-command status refresh failed", exc_info=True)
        return result.speech_reply or "Done."

    async def async_shutdown(self) -> None:
        """Clean up connections."""
        if self._reindex_unsub:
            self._reindex_unsub()
            self._reindex_unsub = None
        if self.jellyfin_client:
            await self.jellyfin_client.async_close()
        if self.navigation_mode:
            await self.navigation_mode.async_deactivate()
