"""Key-event helpers and KEY_MAP for Android TV / Fire TV remote control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ..const import (
    KEY_UP,
    KEY_DOWN,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_SELECT,
    KEY_BACK,
    KEY_HOME,
    KEY_PLAY,
    KEY_PAUSE,
    KEY_STOP,
    KEY_FAST_FORWARD,
    KEY_REWIND,
    KEY_PAGE_UP,
    KEY_PAGE_DOWN,
    KEY_VOLUME_UP,
    KEY_VOLUME_DOWN,
    KEY_MUTE,
)

_LOGGER = logging.getLogger(__name__)

# Android KeyEvent keycodes
# https://developer.android.com/reference/android/view/KeyEvent
KEY_MAP: dict[str, int] = {
    KEY_UP: 19,
    KEY_DOWN: 20,
    KEY_LEFT: 21,
    KEY_RIGHT: 22,
    KEY_SELECT: 23,       # DPAD_CENTER
    KEY_BACK: 4,
    KEY_HOME: 3,
    KEY_PLAY: 126,        # MEDIA_PLAY
    KEY_PAUSE: 127,       # MEDIA_PAUSE
    KEY_STOP: 86,         # MEDIA_STOP
    KEY_FAST_FORWARD: 90, # MEDIA_FAST_FORWARD
    KEY_REWIND: 89,       # MEDIA_REWIND
    KEY_PAGE_UP: 92,
    KEY_PAGE_DOWN: 93,
    KEY_VOLUME_UP: 24,
    KEY_VOLUME_DOWN: 25,
    KEY_MUTE: 164,
}


async def send_key(
    hass: HomeAssistant,
    entity_id: str,
    key: str,
    repeat: int = 1,
) -> None:
    """Send a key event to an Android TV media_player entity.

    Tries the androidtv.adb_command service first; falls back to
    media_player.play_media with a key:// URI so users without the
    androidtv integration can still use other compatible integrations.

    :param hass: HomeAssistant instance.
    :param entity_id: The media_player entity ID of the Android TV.
    :param key: A KEY_* constant string from const.py.
    :param repeat: Number of times to send the key (default 1).
    """
    keycode = KEY_MAP.get(key)
    if keycode is None:
        _LOGGER.warning("Unknown key constant: %s", key)
        return

    for _ in range(repeat):
        if _has_androidtv_service(hass):
            await _send_via_androidtv(hass, entity_id, keycode)
        else:
            await _send_via_media_player(hass, entity_id, key)


def _has_androidtv_service(hass: HomeAssistant) -> bool:
    return hass.services.has_service("androidtv", "adb_command")


async def _send_via_androidtv(
    hass: HomeAssistant, entity_id: str, keycode: int
) -> None:
    service_data: dict[str, Any] = {
        "entity_id": entity_id,
        "command": f"input keyevent {keycode}",
    }
    try:
        await hass.services.async_call(
            "androidtv", "adb_command", service_data, blocking=True
        )
    except Exception as exc:
        _LOGGER.error("androidtv.adb_command failed: %s", exc)


async def _send_via_media_player(
    hass: HomeAssistant, entity_id: str, key: str
) -> None:
    service_data: dict[str, Any] = {
        "entity_id": entity_id,
        "media_content_type": "channel",
        "media_content_id": f"key://{key}",
    }
    try:
        await hass.services.async_call(
            "media_player", "play_media", service_data, blocking=True
        )
    except Exception as exc:
        _LOGGER.debug("media_player.play_media key fallback failed: %s", exc)
