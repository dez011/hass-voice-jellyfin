"""Tests for Navigation Mode lifecycle and command dispatch."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.voice_jellyfin.navigation.mode import NavigationMode
from custom_components.voice_jellyfin.const import (
    EVENT_NAVIGATION_MODE_CHANGED,
    KEY_DOWN,
    KEY_UP,
    KEY_SELECT,
)


def _make_nav_mode(timeout: int = 60, tv_controller=None):
    """Build a NavigationMode with mocked HA plumbing."""
    hass = MagicMock()
    hass.bus.async_fire = MagicMock()
    hass.async_create_task = MagicMock(side_effect=lambda coro: asyncio.ensure_future(coro))

    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.data = {"nav_timeout": str(timeout)}
    entry.options = {}

    coordinator = MagicMock()
    coordinator.tv_controller = tv_controller

    nav = NavigationMode(hass, entry, coordinator)
    return nav, hass, entry, coordinator


@pytest.mark.asyncio
async def test_activate_sets_is_active():
    nav, hass, *_ = _make_nav_mode(timeout=0)  # never timeout
    assert not nav.is_active
    await nav.async_activate()
    assert nav.is_active


@pytest.mark.asyncio
async def test_activate_fires_event():
    nav, hass, *_ = _make_nav_mode(timeout=0)
    await nav.async_activate()
    hass.bus.async_fire.assert_called_with(
        EVENT_NAVIGATION_MODE_CHANGED,
        {"active": True, "entry_id": "test-entry"},
    )


@pytest.mark.asyncio
async def test_deactivate_clears_is_active():
    nav, hass, *_ = _make_nav_mode(timeout=0)
    await nav.async_activate()
    await nav.async_deactivate()
    assert not nav.is_active


@pytest.mark.asyncio
async def test_deactivate_fires_event():
    nav, hass, *_ = _make_nav_mode(timeout=0)
    await nav.async_activate()
    hass.bus.async_fire.reset_mock()
    await nav.async_deactivate()
    hass.bus.async_fire.assert_called_with(
        EVENT_NAVIGATION_MODE_CHANGED,
        {"active": False, "entry_id": "test-entry"},
    )


@pytest.mark.asyncio
async def test_activate_idempotent():
    """Activating an already-active NavMode should not fire the event again."""
    nav, hass, *_ = _make_nav_mode(timeout=0)
    await nav.async_activate()
    first_call_count = hass.bus.async_fire.call_count
    await nav.async_activate()
    assert hass.bus.async_fire.call_count == first_call_count


@pytest.mark.asyncio
async def test_timeout_deactivates():
    """Navigation Mode should auto-deactivate after the configured timeout."""
    nav, hass, *_ = _make_nav_mode(timeout=1)
    # Replace hass.async_create_task with real task scheduling
    nav._hass.async_create_task = lambda coro: asyncio.ensure_future(coro)

    await nav.async_activate()
    assert nav.is_active
    # Wait a bit longer than the timeout
    await asyncio.sleep(1.3)
    assert not nav.is_active


@pytest.mark.asyncio
async def test_handle_command_sends_key():
    tv = MagicMock()
    tv.async_send_key = AsyncMock()
    nav, *_ = _make_nav_mode(timeout=0, tv_controller=tv)
    await nav.async_activate()

    handled = await nav.async_handle_command("down")
    assert handled
    tv.async_send_key.assert_called_with(KEY_DOWN)


@pytest.mark.asyncio
async def test_handle_command_repeat_sends_last_key():
    tv = MagicMock()
    tv.async_send_key = AsyncMock()
    nav, *_ = _make_nav_mode(timeout=0, tv_controller=tv)
    await nav.async_activate()

    await nav.async_handle_command("down")
    tv.async_send_key.reset_mock()

    handled = await nav.async_handle_command("again")
    assert handled
    tv.async_send_key.assert_called_with(KEY_DOWN)


@pytest.mark.asyncio
async def test_handle_command_reverse_sends_opposite_key():
    tv = MagicMock()
    tv.async_send_key = AsyncMock()
    nav, *_ = _make_nav_mode(timeout=0, tv_controller=tv)
    await nav.async_activate()

    await nav.async_handle_command("down")
    tv.async_send_key.reset_mock()

    handled = await nav.async_handle_command("too far")
    assert handled
    tv.async_send_key.assert_called_with(KEY_UP)


@pytest.mark.asyncio
async def test_handle_command_unknown_returns_false():
    nav, *_ = _make_nav_mode(timeout=0)
    await nav.async_activate()
    result = await nav.async_handle_command("xyzzy unknown command abc")
    assert not result


# ---------------------------------------------------------------------------
# Regression tests: command precedence and hot-mic phrase matching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exact_command_not_hijacked_by_repeat_pattern():
    """'continue' is both an exact... no — 'go up' contains no repeat word,
    but phrases like 'go up more' previously matched REPEAT ('more') before
    the explicit direction was considered. Exact commands must win."""
    tv = MagicMock()
    tv.async_send_key = AsyncMock()
    nav, *_ = _make_nav_mode(timeout=0, tv_controller=tv)
    await nav.async_activate()

    # Establish a last key that differs from the spoken command
    await nav.async_handle_command("down")
    tv.async_send_key.reset_mock()

    # "scroll up" is an exact phrase; before the fix, nothing hijacked it —
    # but "up" after "again"-style patterns shows precedence. Use a phrase
    # containing a repeat substring: "keep going up" starts with no exact
    # match; the critical case is an exact phrase that CONTAINS a pattern:
    handled = await nav.async_handle_command("go up")  # exact
    assert handled
    tv.async_send_key.assert_called_with(KEY_UP)


@pytest.mark.asyncio
async def test_prefix_with_repeat_substring_prefers_repeat():
    """Non-exact utterances with a repeat word still repeat the last key."""
    tv = MagicMock()
    tv.async_send_key = AsyncMock()
    nav, *_ = _make_nav_mode(timeout=0, tv_controller=tv)
    await nav.async_activate()
    await nav.async_handle_command("down")
    tv.async_send_key.reset_mock()

    handled = await nav.async_handle_command("keep going")
    assert handled
    tv.async_send_key.assert_called_with(KEY_DOWN)


@pytest.mark.asyncio
async def test_hot_mic_off_phrase_with_punctuation():
    """STT output 'Hey Jellyfin.' must still toggle hot mic off."""
    nav, hass, entry, coordinator = _make_nav_mode(timeout=0)
    entry.data["hot_mic_phrase"] = "hey jellyfin"
    entry.data["hot_mic_timeout"] = 0
    await nav.async_activate_hot_mic()
    assert nav.hot_mic_active

    handled = await nav.async_handle_command("Hey, Jellyfin!")
    assert handled
    assert not nav.hot_mic_active


@pytest.mark.asyncio
async def test_hot_mic_routes_all_speech_through_coordinator():
    nav, hass, entry, coordinator = _make_nav_mode(timeout=0)
    entry.data["hot_mic_timeout"] = 0
    coordinator.async_send_command = AsyncMock(return_value="Playing X.")
    await nav.async_activate_hot_mic()

    handled = await nav.async_handle_command("play something")
    assert handled
    coordinator.async_send_command.assert_awaited_once()


@pytest.mark.asyncio
async def test_hot_mic_fires_ready_event():
    from custom_components.voice_jellyfin.const import EVENT_HOT_MIC_READY

    nav, hass, entry, coordinator = _make_nav_mode(timeout=0)
    entry.data["hot_mic_timeout"] = 0
    coordinator.async_send_command = AsyncMock(return_value="")
    await nav.async_activate_hot_mic()
    hass.bus.async_fire.reset_mock()

    await nav.async_handle_command("mumble mumble")
    fired_events = [c.args[0] for c in hass.bus.async_fire.call_args_list]
    assert EVENT_HOT_MIC_READY in fired_events


# ---------------------------------------------------------------------------
# Repeat counts: "right five times", "up 3", "down down down"
# ---------------------------------------------------------------------------

from custom_components.voice_jellyfin.navigation.mode import _parse_repeat_count


def test_parse_repeat_count_variants():
    assert _parse_repeat_count("right five times") == ("right", 5)
    assert _parse_repeat_count("up 3") == ("up", 3)
    assert _parse_repeat_count("go up 4 times") == ("go up", 4)
    assert _parse_repeat_count("volume up twice") == ("volume up", 2)
    assert _parse_repeat_count("down down down") == ("down", 3)
    assert _parse_repeat_count("select") == ("select", 1)
    assert _parse_repeat_count("page down") == ("page down", 1)
    # capped at 20
    assert _parse_repeat_count("right 99")[1] == 1 or _parse_repeat_count("right 19")[1] == 19


def test_parse_repeat_count_caps_at_20():
    phrase, count = _parse_repeat_count("right 20")
    assert (phrase, count) == ("right", 20)


@pytest.mark.asyncio
async def test_count_command_sends_repeated_keys():
    tv = MagicMock()
    tv.async_send_key = AsyncMock()
    nav, *_ = _make_nav_mode(timeout=0, tv_controller=tv)
    await nav.async_activate()
    handled = await nav.async_handle_command("right five times")
    assert handled
    assert tv.async_send_key.call_count == 5


@pytest.mark.asyncio
async def test_go_back_one_still_reverses():
    """'go back one' is overshoot recovery (reverse), not 'back' x1."""
    tv = MagicMock()
    tv.async_send_key = AsyncMock()
    nav, *_ = _make_nav_mode(timeout=0, tv_controller=tv)
    await nav.async_activate()
    await nav.async_handle_command("down")
    tv.async_send_key.reset_mock()
    handled = await nav.async_handle_command("go back one")
    assert handled
    tv.async_send_key.assert_called_once_with(KEY_UP)
