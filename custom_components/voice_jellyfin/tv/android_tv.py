"""High-level Android TV controller built on top of the remote helpers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from . import remote

_LOGGER = logging.getLogger(__name__)


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

    async def async_launch_app(self, package_name: str) -> bool:
        """Launch an installed app by package name. Returns True on apparent success."""
        try:
            await self._hass.services.async_call(
                "media_player",
                "select_source",
                {"entity_id": self._entity_id, "source": package_name},
                blocking=True,
            )
            return True
        except Exception:
            pass
        result = await self._adb_command(f"am start -n {package_name}/.MainActivity")
        if "error" in result.lower() or "exception" in result.lower():
            _LOGGER.warning("App launch may have failed for %s: %s", package_name, result)
            return False
        return True

    async def async_deep_link(self, uri: str, package: str | None = None) -> bool:
        """Open a URI using the Android VIEW intent via ADB. Returns True on success."""
        cmd = f"am start -a android.intent.action.VIEW -d '{uri}'"
        if package:
            cmd += f" -p {package}"
        try:
            result = await self._adb_command(cmd)
            if "error" in result.lower() or "exception" in result.lower():
                _LOGGER.warning("Deep link failed for %s: %s", uri, result)
                return False
            return True
        except Exception as exc:
            _LOGGER.error("Deep link error for %s: %s", uri, exc)
            return False

    # ------------------------------------------------------------------
    # Wake
    # ------------------------------------------------------------------

    async def async_wake(self) -> None:
        """Send a wake signal to the TV (fire-and-forget — does not wait for boot)."""
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

        try:
            await self._hass.services.async_call(
                "media_player",
                "turn_on",
                {"entity_id": self._entity_id},
                blocking=True,
            )
        except Exception as exc:
            _LOGGER.warning("Wake TV failed: %s", exc)

    async def async_ensure_awake(self, timeout: float = 30.0) -> bool:
        """Wake the TV and poll until it responds (or timeout). Returns True if awake."""
        await self.async_wake()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            state = self._hass.states.get(self._entity_id)
            if state and state.state not in ("off", "unavailable", "unknown"):
                return True
            # Also test ADB responsiveness directly
            if remote._has_androidtv_service(self._hass):
                try:
                    await self._hass.services.async_call(
                        "androidtv",
                        "adb_command",
                        {"entity_id": self._entity_id, "command": "input keyevent 0"},
                        blocking=True,
                    )
                    return True
                except Exception:
                    pass
            await asyncio.sleep(2.0)
        _LOGGER.warning("TV %s did not become responsive within %.0fs", self._entity_id, timeout)
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _adb_command(self, cmd: str) -> str:
        """Execute a raw ADB shell command via the androidtv integration. Returns output or ''."""
        if remote._has_androidtv_service(self._hass):
            try:
                await self._hass.services.async_call(
                    "androidtv",
                    "adb_command",
                    {"entity_id": self._entity_id, "command": cmd},
                    blocking=True,
                )
                return ""
            except Exception as exc:
                _LOGGER.error("ADB command '%s' failed: %s", cmd, exc)
                return "error"
        else:
            _LOGGER.debug("androidtv service not available; skipping: %s", cmd)
            return ""
