"""Tests for the Voice Jellyfin config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def flow(mock_hass):
    """Instantiate a fresh config flow handler."""
    from custom_components.voice_jellyfin.config_flow import VoiceJellyfinConfigFlow

    flow = VoiceJellyfinConfigFlow()
    flow.hass = mock_hass
    flow._data = {}
    # Provide a minimal async_create_entry / async_show_form mock
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry", "data": flow._data})
    flow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
    return flow


@pytest.mark.asyncio
async def test_step_user_shows_form(flow):
    """Step 1 (user) with no input should present the Jellyfin form."""
    result = await flow.async_step_user()
    assert result["type"] == "form"
    assert result["step_id"] == "jellyfin"


@pytest.mark.asyncio
async def test_step_user_advances_to_jellyfin(flow):
    """Submitting step 1 should advance to the Jellyfin step."""
    flow.async_step_jellyfin = AsyncMock(return_value={"type": "form", "step_id": "jellyfin"})
    result = await flow.async_step_user({"network_mode": "local"})
    flow.async_step_jellyfin.assert_called_once()
    assert result["step_id"] == "jellyfin"


@pytest.mark.asyncio
async def test_step_jellyfin_connection_error(flow):
    """A bad Jellyfin URL should return an error on the jellyfin step."""
    with patch(
        "custom_components.voice_jellyfin.jellyfin.client.JellyfinClient"
    ) as MockClient:
        MockClient.return_value.async_connect = AsyncMock(
            side_effect=ConnectionError("refused")
        )
        MockClient.return_value.async_close = AsyncMock()
        result = await flow.async_step_jellyfin(
            {"jellyfin_url": "http://bad-host:8096", "jellyfin_api_key": "key"}
        )
    assert result["type"] == "form"
    assert result.get("errors", {}).get("base") == "cannot_connect"


@pytest.mark.asyncio
async def test_step_jellyfin_success_advances_to_jellyfin_user(flow):
    """A valid Jellyfin connection should advance to the user picker (which
    fetched /Users during the connection) before the TV device chooser."""
    flow.async_step_jellyfin_user = AsyncMock(return_value={"type": "form", "step_id": "jellyfin_user"})
    with patch(
        "custom_components.voice_jellyfin.jellyfin.client.JellyfinClient"
    ) as MockClient:
        MockClient.return_value.async_connect = AsyncMock(return_value={"Version": "10.9"})
        MockClient.return_value.async_close = AsyncMock()
        MockClient.return_value.async_get_users = AsyncMock(
            return_value=[{"id": "u1", "name": "Miguel"}]
        )
        result = await flow.async_step_jellyfin(
            {"jellyfin_url": "http://localhost:8096", "jellyfin_api_key": "abc"}
        )
    flow.async_step_jellyfin_user.assert_called_once()
    assert result["step_id"] == "jellyfin_user"
    assert flow._data["_jellyfin_users"] == [{"id": "u1", "name": "Miguel"}]


@pytest.mark.asyncio
async def test_step_jellyfin_user_list_failure_does_not_block_setup(flow):
    """If /Users can't be listed, setup still proceeds with just Auto-detect."""
    flow.async_step_jellyfin_user = AsyncMock(return_value={"type": "form", "step_id": "jellyfin_user"})
    with patch(
        "custom_components.voice_jellyfin.jellyfin.client.JellyfinClient"
    ) as MockClient:
        MockClient.return_value.async_connect = AsyncMock(return_value={"Version": "10.9"})
        MockClient.return_value.async_close = AsyncMock()
        MockClient.return_value.async_get_users = AsyncMock(side_effect=Exception("403"))
        result = await flow.async_step_jellyfin(
            {"jellyfin_url": "http://localhost:8096", "jellyfin_api_key": "abc"}
        )
    assert result["step_id"] == "jellyfin_user"
    assert flow._data["_jellyfin_users"] == []


@pytest.mark.asyncio
async def test_step_jellyfin_user_picks_default_user_and_advances(flow):
    flow.async_step_tv_device = AsyncMock(return_value={"type": "form", "step_id": "tv_device"})
    flow._data["_jellyfin_users"] = [{"id": "u1", "name": "Miguel"}]
    result = await flow.async_step_jellyfin_user({"jellyfin_default_user": "u1"})
    flow.async_step_tv_device.assert_called_once()
    assert result["step_id"] == "tv_device"
    assert flow._data["jellyfin_default_user"] == "u1"
    assert "_jellyfin_users" not in flow._data


@pytest.mark.asyncio
async def test_step_jellyfin_user_shows_auto_detect_option(flow):
    flow._data["_jellyfin_users"] = [{"id": "u1", "name": "Miguel"}, {"id": "u2", "name": "Brother"}]
    result = await flow.async_step_jellyfin_user()
    assert result["type"] == "form"
    assert result["step_id"] == "jellyfin_user"


@pytest.mark.asyncio
async def test_step_android_tv_shows_form(flow):
    """Android TV step with no input should present the form."""
    result = await flow.async_step_android_tv()
    assert result["type"] == "form"
    assert result["step_id"] == "android_tv"


@pytest.mark.asyncio
async def test_step_android_tv_advances_to_ai_provider(flow):
    """Submitting the Android TV step should advance to AI provider."""
    flow.async_step_ai_provider = AsyncMock(return_value={"type": "form", "step_id": "ai_provider"})
    await flow.async_step_android_tv(
        {"android_tv_entity": "media_player.tv", "adb_port": 5555, "tv_wake_support": True}
    )
    flow.async_step_ai_provider.assert_called_once()


@pytest.mark.asyncio
async def test_step_ai_provider_ollama_path(flow):
    """Choosing Ollama should route to the ollama sub-step."""
    flow.async_step_ollama = AsyncMock(return_value={"type": "form", "step_id": "ollama"})
    await flow.async_step_ai_provider({"ai_provider": "ollama"})
    flow.async_step_ollama.assert_called_once()


@pytest.mark.asyncio
async def test_step_ollama_connection_failure(flow):
    """Ollama step should show error if models cannot be listed."""
    with patch(
        "custom_components.voice_jellyfin.ai.providers.ollama.OllamaProvider"
    ) as MockOllama:
        MockOllama.async_list_models = AsyncMock(side_effect=Exception("timeout"))
        result = await flow.async_step_ollama(
            {
                "ollama_host": "localhost",
                "ollama_port": 11434,
                "ollama_https": False,
                "ollama_model": "llama3",
                "ollama_context_size": 4096,
                "ollama_keep_alive": "5m",
                "ai_streaming": True,
                "ai_timeout": 15,
            }
        )
    assert result.get("errors", {}).get("base") == "cannot_connect"


@pytest.mark.asyncio
async def test_step_ollama_success_advances_to_model_picker(flow):
    """Successful Ollama connection advances to the model picker step."""
    flow.async_step_ollama_model = AsyncMock(
        return_value={"type": "form", "step_id": "ollama_model"}
    )
    with patch(
        "custom_components.voice_jellyfin.ai.providers.ollama.OllamaProvider"
    ) as MockOllama:
        MockOllama.async_list_models = AsyncMock(return_value=["llama3", "mistral"])
        await flow.async_step_ollama(
            {"ollama_host": "localhost", "ollama_port": 11434, "ollama_https": False}
        )
    flow.async_step_ollama_model.assert_called_once()
    assert flow._data["_ollama_models"] == ["llama3", "mistral"]


@pytest.mark.asyncio
async def test_step_ollama_model_advances_to_nav_mode(flow):
    """Picking a model advances to nav_mode."""
    flow.async_step_nav_mode = AsyncMock(return_value={"type": "form", "step_id": "nav_mode"})
    flow._data["_ollama_models"] = ["llama3"]
    await flow.async_step_ollama_model(
        {
            "ollama_model": "llama3",
            "ollama_context_size": 4096,
            "ollama_keep_alive": "5m",
            "ai_streaming": True,
            "ai_timeout": 15,
        }
    )
    flow.async_step_nav_mode.assert_called_once()


@pytest.mark.asyncio
async def test_step_nav_mode_shows_form(flow):
    result = await flow.async_step_nav_mode()
    assert result["type"] == "form"
    assert result["step_id"] == "nav_mode"


@pytest.mark.asyncio
async def test_step_nav_mode_advances_to_accessibility_button(flow):
    flow.async_step_accessibility_button = AsyncMock(
        return_value={"type": "form", "step_id": "accessibility_button"}
    )
    await flow.async_step_nav_mode(
        {
            "nav_wake_phrase": "navigation mode",
            "nav_timeout": "60",
            "nav_continuous": True,
            "nav_confirmation_speech": True,
        }
    )
    flow.async_step_accessibility_button.assert_called_once()


@pytest.mark.asyncio
async def test_full_flow_creates_entry(flow):
    """Completing accessibility_button step should create the config entry."""
    result = await flow.async_step_accessibility_button(
        {"button_entity": "input_button.btn", "button_trigger": "state_changed"}
    )
    flow.async_create_entry.assert_called_once()


# ---------------------------------------------------------------------------
# Regression tests: AI enablement, duplicate guard, options-flow saving
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_choosing_ai_provider_enables_ai(flow):
    """Regression: entries created by the wizard never set ai_enabled, so
    every voice command silently fell back to rule-based intents."""
    flow.async_step_cloud_provider = AsyncMock(return_value={"type": "form"})
    await flow.async_step_ai_provider({"ai_provider": "openai"})
    assert flow._data["ai_enabled"] is True


@pytest.mark.asyncio
async def test_jellyfin_step_sets_unique_id(flow):
    """The server URL becomes the unique id so a server can't be added twice."""
    flow.async_step_tv_device = AsyncMock(return_value={"type": "form"})
    with patch(
        "custom_components.voice_jellyfin.jellyfin.client.JellyfinClient"
    ) as MockClient:
        MockClient.return_value.async_connect = AsyncMock(return_value={"Version": "10.9"})
        MockClient.return_value.async_close = AsyncMock()
        await flow.async_step_jellyfin(
            {"jellyfin_url": "http://MyServer:8096/", "jellyfin_api_key": "abc"}
        )
    assert flow.unique_id == "http://myserver:8096"


def _make_options_flow(entry_data=None, entry_options=None, hass=None):
    from custom_components.voice_jellyfin.config_flow import VoiceJellyfinOptionsFlow

    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = entry_data or {"jellyfin_url": "http://x", "jellyfin_api_key": "SECRET"}
    entry.options = entry_options or {}
    oflow = VoiceJellyfinOptionsFlow(entry)
    oflow.hass = hass or MagicMock()
    oflow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
    captured = {}

    def _create_entry(title="", data=None):
        captured["data"] = data
        return {"type": "create_entry", "data": data}

    oflow.async_create_entry = MagicMock(side_effect=_create_entry)
    return oflow, captured


@pytest.mark.asyncio
async def test_options_save_does_not_clone_entry_data():
    """Regression: every options save copied ALL of entry.data (including
    the Jellyfin API key) into entry.options, permanently shadowing data."""
    oflow, captured = _make_options_flow()
    await oflow.async_step_nav({"nav_timeout": "30"})
    assert captured["data"] == {"nav_timeout": "30"}
    assert "jellyfin_api_key" not in captured["data"]


@pytest.mark.asyncio
async def test_options_save_preserves_existing_options():
    oflow, captured = _make_options_flow(entry_options={"ai_enabled": True})
    await oflow.async_step_nav({"nav_timeout": "30"})
    assert captured["data"] == {"ai_enabled": True, "nav_timeout": "30"}


@pytest.mark.asyncio
async def test_options_ai_disabled_short_circuits():
    oflow, captured = _make_options_flow()
    await oflow.async_step_ai_provider({"ai_enabled": False, "ai_provider": "openai"})
    assert captured["data"]["ai_enabled"] is False
