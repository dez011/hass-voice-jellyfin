"""Navigation Mode runtime — active/idle state management."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import (
    CONF_NAV_TIMEOUT,
    DEFAULT_NAV_TIMEOUT,
    EVENT_NAVIGATION_MODE_CHANGED,
    NAV_TIMEOUT_NEVER,
)
from .commands import VOICE_TO_KEY, REPEAT_PATTERNS, REVERSE_PATTERNS

if TYPE_CHECKING:
    from ..coordinator import VoiceJellyfinCoordinator

_LOGGER = logging.getLogger(__name__)

# Reverse direction map for REVERSE_PATTERNS
_REVERSE_KEY_MAP: dict[str, str] = {
    "up": "down",
    "down": "up",
    "left": "right",
    "right": "left",
    "page_up": "page_down",
    "page_down": "page_up",
    "fast_forward": "rewind",
    "rewind": "fast_forward",
}


class NavigationMode:
    """Manages the Navigation Mode lifecycle for a single config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: "VoiceJellyfinCoordinator",
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self.is_active: bool = False
        self._timeout_task: Optional[asyncio.Task] = None
        self._last_key: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def async_activate(self) -> None:
        """Enter Navigation Mode."""
        if self.is_active:
            self._reset_timeout()
            return
        self.is_active = True
        _LOGGER.info("Navigation Mode activated")
        self._hass.bus.async_fire(
            EVENT_NAVIGATION_MODE_CHANGED,
            {"active": True, "entry_id": self._entry.entry_id},
        )
        self._reset_timeout()

    async def async_deactivate(self) -> None:
        """Exit Navigation Mode."""
        if not self.is_active:
            return
        self.is_active = False
        self._cancel_timeout()
        _LOGGER.info("Navigation Mode deactivated")
        self._hass.bus.async_fire(
            EVENT_NAVIGATION_MODE_CHANGED,
            {"active": False, "entry_id": self._entry.entry_id},
        )

    async def async_handle_command(self, text: str) -> bool:
        """Handle a navigation-mode voice command.

        :param text: Raw voice text.
        :returns: True if the command was handled as a nav key, False otherwise.
        """
        normalized = text.lower().strip()

        # Check repeat patterns
        if any(p in normalized for p in REPEAT_PATTERNS):
            if self._last_key:
                await self._send_key(self._last_key)
                self._reset_timeout()
                return True

        # Check reverse patterns
        if any(p in normalized for p in REVERSE_PATTERNS):
            if self._last_key:
                reverse = _REVERSE_KEY_MAP.get(self._last_key)
                if reverse:
                    await self._send_key(reverse)
                    self._reset_timeout()
                    return True

        # Direct phrase lookup
        key = VOICE_TO_KEY.get(normalized)
        if key is None:
            # Try prefix match for multi-word phrases
            key = next(
                (v for k, v in VOICE_TO_KEY.items() if normalized.startswith(k)),
                None,
            )

        if key:
            await self._send_key(key)
            self._last_key = key
            self._reset_timeout()
            return True

        return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send_key(self, key: str) -> None:
        tv = self._coordinator.tv_controller
        if tv:
            await tv.async_send_key(key)
        else:
            _LOGGER.debug("No TV controller for nav key: %s", key)

    def _reset_timeout(self) -> None:
        self._cancel_timeout()
        timeout = self._get_timeout()
        if timeout != NAV_TIMEOUT_NEVER:
            self._timeout_task = self._hass.async_create_task(
                self._async_timeout_handler(timeout)
            )

    def _cancel_timeout(self) -> None:
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._timeout_task = None

    async def _async_timeout_handler(self, delay: int) -> None:
        """Deactivate Navigation Mode after *delay* seconds of inactivity."""
        try:
            await asyncio.sleep(delay)
            _LOGGER.debug("Navigation Mode timed out after %ds", delay)
            await self.async_deactivate()
        except asyncio.CancelledError:
            pass

    def _get_timeout(self) -> int:
        """Return the configured nav timeout in seconds."""
        raw = (
            self._entry.options.get(CONF_NAV_TIMEOUT)
            or self._entry.data.get(CONF_NAV_TIMEOUT, DEFAULT_NAV_TIMEOUT)
        )
        try:
            return int(raw)
        except (ValueError, TypeError):
            return DEFAULT_NAV_TIMEOUT
