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
