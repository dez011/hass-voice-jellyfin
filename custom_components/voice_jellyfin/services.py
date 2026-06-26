"""Service registration for Voice Jellyfin."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_PLAY,
    SERVICE_SEARCH,
    SERVICE_RESUME,
    SERVICE_PAUSE,
    SERVICE_STOP,
    SERVICE_NAVIGATE,
    SERVICE_SCROLL,
    SERVICE_SELECT,
    SERVICE_NAVIGATION_MODE_ON,
    SERVICE_NAVIGATION_MODE_OFF,
    SERVICE_REPEAT_LAST_ACTION,
    SERVICE_GO_HOME,
    SERVICE_GO_BACK,
    KEY_HOME,
    KEY_BACK,
    KEY_SELECT,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_PLAY_SCHEMA = vol.Schema({
    vol.Required("query"): cv.string,
    vol.Optional("library_id"): cv.string,
})

_SEARCH_SCHEMA = vol.Schema({
    vol.Required("query"): cv.string,
})

_RESUME_SCHEMA = vol.Schema({
    vol.Optional("user_id"): cv.string,
})

_SESSION_SCHEMA = vol.Schema({
    vol.Optional("session_id"): cv.string,
})

_NAVIGATE_SCHEMA = vol.Schema({
    vol.Required("direction"): vol.In([
        "up", "down", "left", "right",
        "select", "back", "home", "page_up", "page_down",
    ]),
})

_SCROLL_SCHEMA = vol.Schema({
    vol.Required("direction"): vol.In(["up", "down"]),
    vol.Optional("amount", default=1): vol.All(int, vol.Range(min=1, max=20)),
})

_EMPTY_SCHEMA = vol.Schema({})


def async_register_services(hass: HomeAssistant) -> None:
    """Register all Voice Jellyfin HA services.

    Safe to call multiple times — skips re-registration if a service
    already exists.
    """

    def _get_coordinators() -> list[Any]:
        return list(hass.data.get(DOMAIN, {}).values())

    # ------------------------------------------------------------------
    # Helper: run a coordinator method, log if none available
    # ------------------------------------------------------------------

    async def _for_all(
        call: ServiceCall, method: str, *args: Any, **kwargs: Any
    ) -> None:
        coordinators = _get_coordinators()
        if not coordinators:
            _LOGGER.warning("No Voice Jellyfin entries loaded")
            return
        for coordinator in coordinators:
            func = getattr(coordinator, method, None)
            if func:
                await func(*args, **kwargs)

    # ------------------------------------------------------------------

    async def handle_play(call: ServiceCall) -> None:
        query = call.data["query"]
        library_id = call.data.get("library_id")
        cmd = f"play {query}"
        if library_id:
            cmd += f" in library {library_id}"
        for coordinator in _get_coordinators():
            await coordinator.async_send_command(cmd)

    async def handle_search(call: ServiceCall) -> None:
        query = call.data["query"]
        for coordinator in _get_coordinators():
            await coordinator.async_send_command(f"search {query}")

    async def handle_resume(call: ServiceCall) -> None:
        user_id = call.data.get("user_id", "")
        for coordinator in _get_coordinators():
            if coordinator.jellyfin_client:
                uid = user_id or coordinator.jellyfin_client._auth.user_id or ""
                await coordinator.jellyfin_client.async_resume(uid)

    async def handle_pause(call: ServiceCall) -> None:
        session_id = call.data.get("session_id")
        for coordinator in _get_coordinators():
            client = coordinator.jellyfin_client
            if client:
                if not session_id:
                    sessions = await client.async_get_sessions()
                    session_id = sessions[0].id if sessions else None
                if session_id:
                    await client.async_pause(session_id)

    async def handle_stop(call: ServiceCall) -> None:
        session_id = call.data.get("session_id")
        for coordinator in _get_coordinators():
            client = coordinator.jellyfin_client
            if client:
                if not session_id:
                    sessions = await client.async_get_sessions()
                    session_id = sessions[0].id if sessions else None
                if session_id:
                    await client.async_stop(session_id)

    async def handle_navigate(call: ServiceCall) -> None:
        direction = call.data["direction"]
        for coordinator in _get_coordinators():
            if coordinator.tv_controller:
                await coordinator.tv_controller.async_send_key(direction)

    async def handle_scroll(call: ServiceCall) -> None:
        direction = call.data["direction"]
        amount = call.data.get("amount", 1)
        for coordinator in _get_coordinators():
            if coordinator.tv_controller:
                for _ in range(amount):
                    await coordinator.tv_controller.async_send_key(direction)

    async def handle_select(call: ServiceCall) -> None:
        for coordinator in _get_coordinators():
            if coordinator.tv_controller:
                await coordinator.tv_controller.async_send_key(KEY_SELECT)

    async def handle_nav_mode_on(call: ServiceCall) -> None:
        for coordinator in _get_coordinators():
            if coordinator.navigation_mode:
                await coordinator.navigation_mode.async_activate()

    async def handle_nav_mode_off(call: ServiceCall) -> None:
        for coordinator in _get_coordinators():
            if coordinator.navigation_mode:
                await coordinator.navigation_mode.async_deactivate()

    async def handle_repeat(call: ServiceCall) -> None:
        for coordinator in _get_coordinators():
            nav = coordinator.navigation_mode
            if nav and nav._last_key:
                if coordinator.tv_controller:
                    await coordinator.tv_controller.async_send_key(nav._last_key)

    async def handle_go_home(call: ServiceCall) -> None:
        for coordinator in _get_coordinators():
            if coordinator.tv_controller:
                await coordinator.tv_controller.async_send_key(KEY_HOME)

    async def handle_go_back(call: ServiceCall) -> None:
        for coordinator in _get_coordinators():
            if coordinator.tv_controller:
                await coordinator.tv_controller.async_send_key(KEY_BACK)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    _register = [
        (SERVICE_PLAY, handle_play, _PLAY_SCHEMA),
        (SERVICE_SEARCH, handle_search, _SEARCH_SCHEMA),
        (SERVICE_RESUME, handle_resume, _RESUME_SCHEMA),
        (SERVICE_PAUSE, handle_pause, _SESSION_SCHEMA),
        (SERVICE_STOP, handle_stop, _SESSION_SCHEMA),
        (SERVICE_NAVIGATE, handle_navigate, _NAVIGATE_SCHEMA),
        (SERVICE_SCROLL, handle_scroll, _SCROLL_SCHEMA),
        (SERVICE_SELECT, handle_select, _EMPTY_SCHEMA),
        (SERVICE_NAVIGATION_MODE_ON, handle_nav_mode_on, _EMPTY_SCHEMA),
        (SERVICE_NAVIGATION_MODE_OFF, handle_nav_mode_off, _EMPTY_SCHEMA),
        (SERVICE_REPEAT_LAST_ACTION, handle_repeat, _EMPTY_SCHEMA),
        (SERVICE_GO_HOME, handle_go_home, _EMPTY_SCHEMA),
        (SERVICE_GO_BACK, handle_go_back, _EMPTY_SCHEMA),
    ]

    for svc_name, handler, schema in _register:
        if not hass.services.has_service(DOMAIN, svc_name):
            hass.services.async_register(DOMAIN, svc_name, handler, schema=schema)
            _LOGGER.debug("Registered service: %s.%s", DOMAIN, svc_name)
