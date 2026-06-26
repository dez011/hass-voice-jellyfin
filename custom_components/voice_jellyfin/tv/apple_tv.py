"""Apple TV controller via HA's built-in Apple TV remote integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ..const import (
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_SELECT, KEY_BACK, KEY_HOME,
    KEY_PLAY, KEY_PAUSE, KEY_STOP,
    KEY_FAST_FORWARD, KEY_REWIND,
    KEY_PAGE_UP, KEY_PAGE_DOWN,
    KEY_VOLUME_UP, KEY_VOLUME_DOWN, KEY_MUTE,
)

_LOGGER = logging.getLogger(__name__)

# Maps our internal KEY_* constants to Apple TV remote.send_command values.
# https://www.home-assistant.io/integrations/apple_tv/#remote
KEY_MAP: dict[str, str] = {
    KEY_UP: "up",
    KEY_DOWN: "down",
    KEY_LEFT: "left",
    KEY_RIGHT: "right",
    KEY_SELECT: "select",
    KEY_BACK: "menu",
    KEY_HOME: "top_menu",
    KEY_PLAY: "play_pause",
    KEY_PAUSE: "play_pause",
    KEY_STOP: "stop",
    KEY_FAST_FORWARD: "skip_forward",
    KEY_REWIND: "skip_backward",
    KEY_PAGE_UP: "channel_up",
    KEY_PAGE_DOWN: "channel_down",
    KEY_VOLUME_UP: "volume_up",
    KEY_VOLUME_DOWN: "volume_down",
    KEY_MUTE: "mute",
}


class AppleTVController:
    """Controls an Apple TV via HA's remote.send_command service."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    async def async_send_key(self, key: str, repeat: int = 1) -> None:
        command = KEY_MAP.get(key)
        if command is None:
            _LOGGER.warning("Unknown key for Apple TV: %s", key)
            return

        service_data: dict[str, Any] = {
            "entity_id": self._entity_id,
            "command": command,
            "num_repeats": repeat,
        }
        try:
            await self._hass.services.async_call(
                "remote", "send_command", service_data, blocking=True
            )
        except Exception as exc:
            _LOGGER.error("Apple TV remote.send_command failed for '%s': %s", command, exc)

    async def async_wake(self) -> None:
        try:
            await self._hass.services.async_call(
                "remote", "turn_on", {"entity_id": self._entity_id}, blocking=True
            )
        except Exception as exc:
            _LOGGER.warning("Apple TV wake failed: %s", exc)
