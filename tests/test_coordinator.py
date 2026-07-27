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
