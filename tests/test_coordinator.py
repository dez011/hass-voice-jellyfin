"""Tests for VoiceJellyfinCoordinator lifecycle and command routing."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.voice_jellyfin.coordinator import VoiceJellyfinCoordinator


def _make_coordinator(mock_hass, mock_config_entry) -> VoiceJellyfinCoordinator:
    coordinator = VoiceJellyfinCoordinator(mock_hass, mock_config_entry)
    coordinator.hass = mock_hass
    return coordinator


@pytest.mark.asyncio
async def test_setup_passes_default_user_to_auth(mock_hass, mock_config_entry):
    """The configured default user must reach JellyfinAuth — an empty user id
    produced malformed /Users//... URLs on every user-scoped endpoint."""
    # Ensure the lazily-imported submodules exist before patching them
    import custom_components.voice_jellyfin.navigation.trigger  # noqa: F401
    import custom_components.voice_jellyfin.navigation.mode  # noqa: F401

    coordinator = _make_coordinator(mock_hass, mock_config_entry)

    captured = {}

    class _FakeAuth:
        def __init__(self, url, api_key="", user_id=None, **kw):
            captured["url"] = url
            captured["user_id"] = user_id

    fake_client = MagicMock()
    fake_client.async_connect = AsyncMock(return_value={"Version": "10.9"})

    def _consume_bg_task(coro, name=None):
        coro.close()
        return MagicMock()

    mock_hass.async_create_background_task = MagicMock(side_effect=_consume_bg_task)

    with patch("custom_components.voice_jellyfin.jellyfin.auth.JellyfinAuth", _FakeAuth), \
         patch("custom_components.voice_jellyfin.jellyfin.client.JellyfinClient", return_value=fake_client), \
         patch("custom_components.voice_jellyfin.navigation.mode.NavigationMode"), \
         patch("custom_components.voice_jellyfin.navigation.trigger.ButtonTrigger") as trigger_cls, \
         patch("custom_components.voice_jellyfin.ai.providers.build_provider", new=AsyncMock(return_value=None)):
        trigger_cls.return_value.async_attach = AsyncMock()
        coordinator.async_refresh = AsyncMock()
        await coordinator.async_setup()

    assert captured["user_id"] == "user-id-xyz"


@pytest.mark.asyncio
async def test_send_command_uses_merged_tv_type(mock_hass, mock_config_entry):
    """tv_type must come from data+options — options-flow changes were
    ignored until restart when only entry.data was read."""
    mock_config_entry.data = {**mock_config_entry.data, "tv_type": "android_tv"}
    mock_config_entry.options = {"tv_type": "apple_tv"}
    coordinator = _make_coordinator(mock_hass, mock_config_entry)
    coordinator.jellyfin_client = MagicMock()
    coordinator.ai_provider = None
    coordinator.ai_context = MagicMock()
    coordinator.navigation_mode = None
    coordinator.async_set_updated_data = MagicMock()
    coordinator._async_update_data = AsyncMock(return_value={})

    captured = {}

    class _FakeRouter:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self._bitrate_idx = -1

        async def async_route(self, *a, **kw):
            from custom_components.voice_jellyfin.ai.intent_router import IntentResult
            return IntentResult(intent="SEARCH")

    with patch("custom_components.voice_jellyfin.ai.intent_router.IntentRouter", _FakeRouter):
        await coordinator.async_send_command("search something")

    assert captured["tv_type"] == "apple_tv"


@pytest.mark.asyncio
async def test_shutdown_detaches_button_trigger_and_cancels_catalog(mock_hass, mock_config_entry):
    """Regression: reloading an entry leaked the global state_changed
    listener and left the catalog index task running on a closed client."""
    coordinator = _make_coordinator(mock_hass, mock_config_entry)
    coordinator.jellyfin_client = MagicMock()
    coordinator.jellyfin_client.async_close = AsyncMock()
    coordinator.navigation_mode = MagicMock()
    coordinator.navigation_mode.async_deactivate = AsyncMock()
    trigger = MagicMock()
    coordinator.button_trigger = trigger
    catalog_task = MagicMock()
    coordinator._catalog_task = catalog_task

    await coordinator.async_shutdown()

    trigger.async_detach.assert_called_once()
    catalog_task.cancel.assert_called_once()
    coordinator.jellyfin_client.async_close.assert_awaited_once()
    assert coordinator.button_trigger is None
    assert coordinator._catalog_task is None


@pytest.mark.asyncio
async def test_hot_mic_phrase_matches_with_punctuation(mock_hass, mock_config_entry):
    """STT output like 'Hey Jellyfin.' must toggle hot mic."""
    mock_config_entry.data = {**mock_config_entry.data, "hot_mic_phrase": "hey jellyfin"}
    coordinator = _make_coordinator(mock_hass, mock_config_entry)
    nav = MagicMock()
    nav._get_hot_mic_phrase = MagicMock(return_value="hey jellyfin")
    nav.async_toggle_hot_mic = AsyncMock()
    nav.hot_mic_active = True
    coordinator.navigation_mode = nav

    reply = await coordinator.async_send_command("Hey, Jellyfin!")
    nav.async_toggle_hot_mic.assert_awaited_once()
    assert "Hot mic" in reply


# ---------------------------------------------------------------------------
# async_handle_voice — the STT routing entry point
# ---------------------------------------------------------------------------

def _voice_coordinator(mock_hass, mock_config_entry):
    coordinator = _make_coordinator(mock_hass, mock_config_entry)
    nav = MagicMock()
    nav.is_active = False
    nav.hot_mic_active = False
    nav.async_activate = AsyncMock()
    nav.async_deactivate = AsyncMock()
    nav.async_handle_command = AsyncMock(return_value=True)
    coordinator.navigation_mode = nav
    coordinator.async_send_command = AsyncMock(return_value="Done.")
    return coordinator, nav


@pytest.mark.asyncio
async def test_voice_wake_phrase_activates_nav_mode(mock_hass, mock_config_entry):
    coordinator, nav = _voice_coordinator(mock_hass, mock_config_entry)
    reply = await coordinator.async_handle_voice("Navigation mode.")
    nav.async_activate.assert_awaited_once()
    coordinator.async_send_command.assert_not_called()
    assert "on" in reply.lower()


@pytest.mark.asyncio
async def test_voice_off_phrase_deactivates_nav_mode(mock_hass, mock_config_entry):
    coordinator, nav = _voice_coordinator(mock_hass, mock_config_entry)
    nav.is_active = True
    reply = await coordinator.async_handle_voice("exit navigation mode")
    nav.async_deactivate.assert_awaited_once()
    assert "off" in reply.lower()


@pytest.mark.asyncio
async def test_voice_routes_keys_while_nav_active(mock_hass, mock_config_entry):
    coordinator, nav = _voice_coordinator(mock_hass, mock_config_entry)
    nav.is_active = True
    reply = await coordinator.async_handle_voice("down")
    nav.async_handle_command.assert_awaited_once_with("down")
    coordinator.async_send_command.assert_not_called()
    assert reply == ""


@pytest.mark.asyncio
async def test_voice_falls_through_to_media_pipeline(mock_hass, mock_config_entry):
    """Unrecognized nav phrases and normal speech reach the full pipeline."""
    coordinator, nav = _voice_coordinator(mock_hass, mock_config_entry)
    nav.is_active = True
    nav.async_handle_command = AsyncMock(return_value=False)  # not a nav key
    await coordinator.async_handle_voice("play inception")
    coordinator.async_send_command.assert_awaited_once_with("play inception")


@pytest.mark.asyncio
async def test_voice_inactive_nav_goes_straight_to_pipeline(mock_hass, mock_config_entry):
    coordinator, nav = _voice_coordinator(mock_hass, mock_config_entry)
    await coordinator.async_handle_voice("play inception")
    nav.async_handle_command.assert_not_called()
    coordinator.async_send_command.assert_awaited_once_with("play inception")


@pytest.mark.asyncio
async def test_setup_uses_adb_controller_without_entity(mock_hass, mock_config_entry):
    """tv_type android + adb_host but no media_player entity must produce a
    working TV controller (previously tv_controller stayed None)."""
    import custom_components.voice_jellyfin.navigation.trigger  # noqa: F401
    import custom_components.voice_jellyfin.navigation.mode  # noqa: F401
    from custom_components.voice_jellyfin.tv.adb import ADBTVController

    data = dict(mock_config_entry.data)
    data.pop("android_tv_entity", None)
    data["tv_type"] = "android_tv"
    data["adb_host"] = "192.168.1.50"
    data["adb_port"] = 5555
    mock_config_entry.data = data

    coordinator = _make_coordinator(mock_hass, mock_config_entry)

    def _consume_bg_task(coro, name=None):
        coro.close()
        return MagicMock()

    mock_hass.async_create_background_task = MagicMock(side_effect=_consume_bg_task)

    fake_client = MagicMock()
    fake_client.async_connect = AsyncMock(return_value={"Version": "10.9"})

    with patch("custom_components.voice_jellyfin.jellyfin.client.JellyfinClient", return_value=fake_client), \
         patch("custom_components.voice_jellyfin.navigation.mode.NavigationMode"), \
         patch("custom_components.voice_jellyfin.navigation.trigger.ButtonTrigger") as trigger_cls, \
         patch("custom_components.voice_jellyfin.ai.providers.build_provider", new=AsyncMock(return_value=None)):
        trigger_cls.return_value.async_attach = AsyncMock()
        coordinator.async_refresh = AsyncMock()
        await coordinator.async_setup()

    assert isinstance(coordinator.tv_controller, ADBTVController)
    assert coordinator._current_device == "adb://192.168.1.50:5555"


# ---------------------------------------------------------------------------
# now_playing computation and target-device wiring
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_update_data_computes_now_playing(mock_hass, mock_config_entry):
    from custom_components.voice_jellyfin.jellyfin.models import MediaItem, PlaybackSession

    coordinator = _make_coordinator(mock_hass, mock_config_entry)
    coordinator.navigation_mode = None
    coordinator._target_device = ""
    client = MagicMock()
    client.async_get_sessions = AsyncMock(return_value=[
        PlaybackSession(
            id="s1", user_id="u1",
            item=MediaItem(id="i1", name="The Matrix", type="Movie"),
            is_paused=False, client="Astra", device_name="Bedroom", user_name="Brother",
        )
    ])
    coordinator.jellyfin_client = client

    data = await coordinator._async_update_data()
    assert data["now_playing"] == {
        "title": "The Matrix", "client": "Astra", "device": "Bedroom",
        "user": "Brother", "paused": False,
    }


@pytest.mark.asyncio
async def test_async_update_data_now_playing_none_when_nothing_playing(mock_hass, mock_config_entry):
    coordinator = _make_coordinator(mock_hass, mock_config_entry)
    coordinator.navigation_mode = None
    coordinator._target_device = ""
    client = MagicMock()
    client.async_get_sessions = AsyncMock(return_value=[])
    coordinator.jellyfin_client = client

    data = await coordinator._async_update_data()
    assert data["now_playing"] is None


@pytest.mark.asyncio
async def test_async_update_data_now_playing_respects_target_device(mock_hass, mock_config_entry):
    from custom_components.voice_jellyfin.jellyfin.models import MediaItem, PlaybackSession

    coordinator = _make_coordinator(mock_hass, mock_config_entry)
    coordinator.navigation_mode = None
    coordinator._target_device = "Living Room"
    client = MagicMock()
    client.async_get_sessions = AsyncMock(return_value=[
        PlaybackSession(id="s1", user_id="u1", item=MediaItem(id="i1", name="Other", type="Movie"), device_name="Bedroom"),
    ])
    coordinator.jellyfin_client = client

    data = await coordinator._async_update_data()
    # "Living Room" has no sessions at all, so pick_now_playing falls back
    # to the only real session (Bedroom) rather than silently returning None.
    assert data["now_playing"]["title"] == "Other"


@pytest.mark.asyncio
async def test_setup_reads_target_device_from_config(mock_hass, mock_config_entry):
    import custom_components.voice_jellyfin.navigation.trigger  # noqa: F401
    import custom_components.voice_jellyfin.navigation.mode  # noqa: F401

    data = dict(mock_config_entry.data)
    data["jellyfin_target_device"] = "Living Room"
    mock_config_entry.data = data

    coordinator = _make_coordinator(mock_hass, mock_config_entry)

    def _consume_bg_task(coro, name=None):
        coro.close()
        return MagicMock()

    mock_hass.async_create_background_task = MagicMock(side_effect=_consume_bg_task)
    fake_client = MagicMock()
    fake_client.async_connect = AsyncMock(return_value={"Version": "10.9"})

    with patch("custom_components.voice_jellyfin.jellyfin.client.JellyfinClient", return_value=fake_client), \
         patch("custom_components.voice_jellyfin.navigation.mode.NavigationMode"), \
         patch("custom_components.voice_jellyfin.navigation.trigger.ButtonTrigger") as trigger_cls, \
         patch("custom_components.voice_jellyfin.ai.providers.build_provider", new=AsyncMock(return_value=None)):
        trigger_cls.return_value.async_attach = AsyncMock()
        coordinator.async_refresh = AsyncMock()
        await coordinator.async_setup()

    assert coordinator._target_device == "Living Room"
