"""Tests for AppleTVController."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.voice_jellyfin.tv.apple_tv import AppleTVController

ENTITY_ID = "remote.living_room_apple_tv"


def _hass():
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.mark.asyncio
async def test_send_key_maps_to_remote_command():
    hass = _hass()
    ctrl = AppleTVController(hass, ENTITY_ID)
    await ctrl.async_send_key("select")
    hass.services.async_call.assert_awaited_once()
    args = hass.services.async_call.call_args[0]
    assert args[0] == "remote" and args[1] == "send_command"
    assert args[2]["command"] == "select"


@pytest.mark.asyncio
async def test_play_and_pause_are_distinct_commands():
    """Regression: both used to map to play_pause, so 'pause' while paused
    would resume playback instead."""
    hass = _hass()
    ctrl = AppleTVController(hass, ENTITY_ID)
    await ctrl.async_send_key("play")
    play_cmd = hass.services.async_call.call_args[0][2]["command"]
    hass.services.async_call.reset_mock()
    await ctrl.async_send_key("pause")
    pause_cmd = hass.services.async_call.call_args[0][2]["command"]
    assert play_cmd != pause_cmd


@pytest.mark.asyncio
async def test_unknown_key_is_ignored():
    hass = _hass()
    ctrl = AppleTVController(hass, ENTITY_ID)
    await ctrl.async_send_key("warp_speed")
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_wake_calls_remote_turn_on():
    hass = _hass()
    ctrl = AppleTVController(hass, ENTITY_ID)
    await ctrl.async_wake()
    hass.services.async_call.assert_awaited_once_with(
        "remote", "turn_on", {"entity_id": ENTITY_ID}, blocking=True
    )


@pytest.mark.asyncio
async def test_launch_app_returns_false_with_clear_signal():
    """Apple TV has no generic app-launch call — this must return False so
    the caller gives a clear 'couldn't open Jellyfin' reply instead of
    crashing into a generic dispatch error (AppleTVController previously
    had no async_launch_app method at all)."""
    hass = _hass()
    ctrl = AppleTVController(hass, ENTITY_ID)
    result = await ctrl.async_launch_app("org.jellyfin.androidtv")
    assert result is False
    hass.services.async_call.assert_not_called()
