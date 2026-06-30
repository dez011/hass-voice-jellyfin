"""DataUpdateCoordinator and shared runtime state for Voice Jellyfin."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

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
        self.async_set_updated_data(await self._async_update_data())
        return result.speech_reply or "Done."

    async def async_shutdown(self) -> None:
        """Clean up connections."""
        if self.jellyfin_client:
            await self.jellyfin_client.async_close()
        if self.navigation_mode:
            await self.navigation_mode.async_deactivate()
