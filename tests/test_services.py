"""Tests for service registration and dispatch."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.voice_jellyfin.const import DOMAIN


def _make_mock_coordinator():
    coord = MagicMock()
    coord.async_send_command = AsyncMock(return_value="Done.")
    coord.jellyfin_client = MagicMock()
    coord.jellyfin_client.async_get_sessions = AsyncMock(return_value=[])
    coord.jellyfin_client.async_pause = AsyncMock()
    coord.jellyfin_client.async_stop = AsyncMock()
    coord.jellyfin_client.async_resume = AsyncMock(return_value="Something")
    coord.jellyfin_client._auth = MagicMock()
    coord.jellyfin_client._auth.user_id = "user-001"
    coord.tv_controller = MagicMock()
    coord.tv_controller.async_send_key = AsyncMock()
    coord.navigation_mode = MagicMock()
    coord.navigation_mode.async_activate = AsyncMock()
    coord.navigation_mode.async_deactivate = AsyncMock()
    coord.navigation_mode._last_key = "down"
    return coord


def _make_hass_with_coordinator(coordinator):
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry-001": coordinator}}
    registered = {}

    def _register(domain, svc, handler, schema=None):
        registered[(domain, svc)] = handler

    def _has_service(domain, svc):
        return (domain, svc) in registered

    hass.services.async_register = MagicMock(side_effect=_register)
    hass.services.has_service = MagicMock(side_effect=_has_service)
    hass._registered = registered
    return hass


@pytest.fixture
def coordinator():
    return _make_mock_coordinator()


@pytest.fixture
def hass_with_services(coordinator):
    hass = _make_hass_with_coordinator(coordinator)
    from custom_components.voice_jellyfin.services import async_register_services
    async_register_services(hass)
    return hass, coordinator, hass._registered


@pytest.mark.asyncio
async def test_all_services_registered(hass_with_services):
    hass, coordinator, registered = hass_with_services
    expected = {
        "play", "search", "resume", "pause", "stop",
        "navigate", "scroll", "select",
        "navigation_mode_on", "navigation_mode_off",
        "repeat_last_action", "go_home", "go_back",
        "reindex_catalog",
    }
    registered_names = {svc for domain, svc in registered.keys() if domain == DOMAIN}
    assert registered_names == expected


@pytest.mark.asyncio
async def test_service_play_calls_send_command(hass_with_services):
    hass, coordinator, registered = hass_with_services
    handler = registered[(DOMAIN, "play")]
    call_obj = MagicMock()
    call_obj.data = {"query": "The Dark Knight"}
    await handler(call_obj)
    coordinator.async_send_command.assert_called_once()
    cmd = coordinator.async_send_command.call_args[0][0]
    assert "The Dark Knight" in cmd


@pytest.mark.asyncio
async def test_service_navigate_calls_tv_controller(hass_with_services):
    hass, coordinator, registered = hass_with_services
    handler = registered[(DOMAIN, "navigate")]
    call_obj = MagicMock()
    call_obj.data = {"direction": "up"}
    await handler(call_obj)
    coordinator.tv_controller.async_send_key.assert_called_with("up")


@pytest.mark.asyncio
async def test_service_navigation_mode_on(hass_with_services):
    hass, coordinator, registered = hass_with_services
    handler = registered[(DOMAIN, "navigation_mode_on")]
    call_obj = MagicMock()
    call_obj.data = {}
    await handler(call_obj)
    coordinator.navigation_mode.async_activate.assert_called_once()


@pytest.mark.asyncio
async def test_service_navigation_mode_off(hass_with_services):
    hass, coordinator, registered = hass_with_services
    handler = registered[(DOMAIN, "navigation_mode_off")]
    call_obj = MagicMock()
    call_obj.data = {}
    await handler(call_obj)
    coordinator.navigation_mode.async_deactivate.assert_called_once()


@pytest.mark.asyncio
async def test_service_go_home_sends_home_key(hass_with_services):
    hass, coordinator, registered = hass_with_services
    handler = registered[(DOMAIN, "go_home")]
    call_obj = MagicMock()
    call_obj.data = {}
    await handler(call_obj)
    coordinator.tv_controller.async_send_key.assert_called_with("home")


@pytest.mark.asyncio
async def test_service_go_back_sends_back_key(hass_with_services):
    hass, coordinator, registered = hass_with_services
    handler = registered[(DOMAIN, "go_back")]
    call_obj = MagicMock()
    call_obj.data = {}
    await handler(call_obj)
    coordinator.tv_controller.async_send_key.assert_called_with("back")


@pytest.mark.asyncio
async def test_service_scroll_sends_multiple_keys(hass_with_services):
    hass, coordinator, registered = hass_with_services
    handler = registered[(DOMAIN, "scroll")]
    call_obj = MagicMock()
    call_obj.data = {"direction": "down", "amount": 3}
    await handler(call_obj)
    assert coordinator.tv_controller.async_send_key.call_count == 3
    coordinator.tv_controller.async_send_key.assert_called_with("down")


@pytest.mark.asyncio
async def test_service_repeat_calls_tv_with_last_key(hass_with_services):
    hass, coordinator, registered = hass_with_services
    handler = registered[(DOMAIN, "repeat_last_action")]
    call_obj = MagicMock()
    call_obj.data = {}
    await handler(call_obj)
    coordinator.tv_controller.async_send_key.assert_called_with("down")


@pytest.mark.asyncio
async def test_services_not_re_registered(coordinator):
    """Calling async_register_services twice should not register duplicates."""
    hass = _make_hass_with_coordinator(coordinator)
    from custom_components.voice_jellyfin.services import async_register_services

    async_register_services(hass)
    first_count = hass.services.async_register.call_count

    async_register_services(hass)
    # Second call: has_service now returns True → no new registrations
    assert hass.services.async_register.call_count == first_count


# ---------------------------------------------------------------------------
# Regression tests: multi-coordinator session handling and play query purity
# ---------------------------------------------------------------------------

def _session_with_item(session_id: str):
    sess = MagicMock()
    sess.id = session_id
    sess.item = MagicMock()
    return sess


@pytest.mark.asyncio
async def test_service_play_does_not_embed_library_guid(coordinator):
    """library_id must never be concatenated into the search text."""
    hass = _make_hass_with_coordinator(coordinator)
    from custom_components.voice_jellyfin.services import async_register_services
    async_register_services(hass)
    handler = hass._registered[(DOMAIN, "play")]
    call_obj = MagicMock()
    call_obj.data = {"query": "Bluey", "library_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"}
    await handler(call_obj)
    cmd = coordinator.async_send_command.call_args[0][0]
    assert "3fa85f64" not in cmd
    assert cmd == "play Bluey"


@pytest.mark.asyncio
async def test_service_pause_resolves_session_per_coordinator():
    """Regression: the first coordinator's session id leaked into the
    second coordinator's pause call."""
    coord_a = _make_mock_coordinator()
    coord_b = _make_mock_coordinator()
    coord_a.jellyfin_client.async_get_sessions = AsyncMock(
        return_value=[_session_with_item("sess-A")]
    )
    coord_b.jellyfin_client.async_get_sessions = AsyncMock(
        return_value=[_session_with_item("sess-B")]
    )

    hass = MagicMock()
    hass.data = {DOMAIN: {"entry-a": coord_a, "entry-b": coord_b}}
    registered = {}
    hass.services.async_register = MagicMock(
        side_effect=lambda d, s, h, schema=None: registered.__setitem__((d, s), h)
    )
    hass.services.has_service = MagicMock(side_effect=lambda d, s: (d, s) in registered)

    from custom_components.voice_jellyfin.services import async_register_services
    async_register_services(hass)

    call_obj = MagicMock()
    call_obj.data = {}
    await registered[(DOMAIN, "pause")](call_obj)

    coord_a.jellyfin_client.async_pause.assert_awaited_once_with("sess-A")
    coord_b.jellyfin_client.async_pause.assert_awaited_once_with("sess-B")


@pytest.mark.asyncio
async def test_service_stop_resolves_session_per_coordinator():
    coord_a = _make_mock_coordinator()
    coord_b = _make_mock_coordinator()
    coord_a.jellyfin_client.async_get_sessions = AsyncMock(
        return_value=[_session_with_item("sess-A")]
    )
    coord_b.jellyfin_client.async_get_sessions = AsyncMock(return_value=[])

    hass = MagicMock()
    hass.data = {DOMAIN: {"entry-a": coord_a, "entry-b": coord_b}}
    registered = {}
    hass.services.async_register = MagicMock(
        side_effect=lambda d, s, h, schema=None: registered.__setitem__((d, s), h)
    )
    hass.services.has_service = MagicMock(side_effect=lambda d, s: (d, s) in registered)

    from custom_components.voice_jellyfin.services import async_register_services
    async_register_services(hass)

    call_obj = MagicMock()
    call_obj.data = {}
    await registered[(DOMAIN, "stop")](call_obj)

    coord_a.jellyfin_client.async_stop.assert_awaited_once_with("sess-A")
    # No session on server B → no stop call with server A's id
    coord_b.jellyfin_client.async_stop.assert_not_called()


@pytest.mark.asyncio
async def test_service_pause_explicit_session_id_used_everywhere():
    coord = _make_mock_coordinator()
    hass = _make_hass_with_coordinator(coord)
    from custom_components.voice_jellyfin.services import async_register_services
    async_register_services(hass)
    call_obj = MagicMock()
    call_obj.data = {"session_id": "explicit-1"}
    await hass._registered[(DOMAIN, "pause")](call_obj)
    coord.jellyfin_client.async_pause.assert_awaited_once_with("explicit-1")
