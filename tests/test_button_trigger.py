"""Tests for the physical accessibility button trigger."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.voice_jellyfin.navigation.trigger import ButtonTrigger


def _make_trigger():
    hass = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    created = []

    def _create_task(coro):
        created.append(coro)
        coro.close()
        return MagicMock()

    hass.async_create_task = MagicMock(side_effect=_create_task)
    coordinator = MagicMock()
    coordinator.navigation_mode = MagicMock()
    coordinator.navigation_mode.async_activate = AsyncMock()
    trigger = ButtonTrigger(hass, "input_button.btn", coordinator)
    return trigger, hass, coordinator, created


def _event(entity_id, old, new):
    event = MagicMock()
    old_state = None if old is None else MagicMock(state=old)
    new_state = None if new is None else MagicMock(state=new)
    event.data = {"entity_id": entity_id, "old_state": old_state, "new_state": new_state}
    return event


@pytest.mark.asyncio
async def test_attach_and_detach():
    trigger, hass, *_ = _make_trigger()
    await trigger.async_attach()
    hass.bus.async_listen.assert_called_once()
    trigger.async_detach()
    assert trigger._unsub is None
    # Detach twice is safe
    trigger.async_detach()


def test_real_transition_activates_nav_mode():
    trigger, hass, coordinator, created = _make_trigger()
    trigger._on_state_change(_event("input_button.btn", "off", "on"))
    assert created, "expected nav activation task"


def test_other_entity_ignored():
    trigger, hass, coordinator, created = _make_trigger()
    trigger._on_state_change(_event("light.kitchen", "off", "on"))
    assert not created


def test_attribute_only_update_ignored():
    """Regression: a light stuck 'on' re-fired state_changed for every
    attribute update and re-armed nav mode endlessly."""
    trigger, hass, coordinator, created = _make_trigger()
    trigger._on_state_change(_event("input_button.btn", "on", "on"))
    assert not created


def test_startup_initial_state_ignored():
    """HA startup emits state_changed with old_state=None — not a press."""
    trigger, hass, coordinator, created = _make_trigger()
    trigger._on_state_change(_event("input_button.btn", None, "on"))
    assert not created


def test_non_trigger_state_ignored():
    trigger, hass, coordinator, created = _make_trigger()
    trigger._on_state_change(_event("input_button.btn", "on", "off"))
    assert not created
