"""High-level Android TV controller built on top of the remote helpers."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from . import remote

_LOGGER = logging.getLogger(__name__)

_JELLYFIN_PACKAGE = "org.jellyfin.androidtv"


class AndroidTVController:
    """Controls an Android TV / Fire TV device via HA services or ADB."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    async def async_send_key(self, key: str, repeat: int = 1) -> None:
        """Send a remote key event (KEY_* constant) to the TV."""
        await remote.send_key(self._hass, self._entity_id, key, repeat)

    # ------------------------------------------------------------------
    # App launch
    # ------------------------------------------------------------------

    async def async_launch_app(self, package_name: str) -> None:
        """Launch an installed app by package name.

        Tries media_player.select_source first (works if the integration
        exposes apps as sources), then falls back to ADB am start.
        """
        try:
            await self._hass.services.async_call(
                "media_player",
                "select_source",
                {"entity_id": self._entity_id, "source": package_name},
                blocking=True,
            )
        except Exception:
            await self._adb_command(f"am start -n {package_name}/.MainActivity")

    async def async_deep_link(self, uri: str) -> None:
        """Open a URI using the Android VIEW intent via ADB."""
        cmd = f"am start -a android.intent.action.VIEW -d '{uri}'"
        await self._adb_command(cmd)

    # ------------------------------------------------------------------
    # Wake
    # ------------------------------------------------------------------

    async def async_wake(self) -> None:
        """Wake the TV screen.

        Tries androidtv.adb_command WAKEUP first; falls back to
        media_player.turn_on.
        """
        if remote._has_androidtv_service(self._hass):
            try:
                await self._hass.services.async_call(
                    "androidtv",
                    "adb_command",
                    {"entity_id": self._entity_id, "command": "WAKEUP"},
                    blocking=True,
                )
                return
            except Exception as exc:
                _LOGGER.debug("WAKEUP via adb_command failed: %s", exc)

        # Fallback: turn_on via media_player
        try:
            await self._hass.services.async_call(
                "media_player",
                "turn_on",
                {"entity_id": self._entity_id},
                blocking=True,
            )
        except Exception as exc:
            _LOGGER.warning("Wake TV failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _adb_command(self, cmd: str) -> None:
        """Execute a raw ADB shell command via the androidtv integration."""
        if remote._has_androidtv_service(self._hass):
            try:
                await self._hass.services.async_call(
                    "androidtv",
                    "adb_command",
                    {"entity_id": self._entity_id, "command": cmd},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("ADB command '%s' failed: %s", cmd, exc)
        else:
            _LOGGER.debug("androidtv service not available; skipping: %s", cmd)
