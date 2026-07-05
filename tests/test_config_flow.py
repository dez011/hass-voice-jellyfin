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
async def test_step_jellyfin_success_advances_to_tv_device(flow):
    """A valid Jellyfin connection should advance to the TV device chooser."""
    flow.async_step_tv_device = AsyncMock(return_value={"type": "form", "step_id": "tv_device"})
    with patch(
        "custom_components.voice_jellyfin.jellyfin.client.JellyfinClient"
    ) as MockClient:
        MockClient.return_value.async_connect = AsyncMock(return_value={"Version": "10.9"})
        MockClient.return_value.async_close = AsyncMock()
        result = await flow.async_step_jellyfin(
            {"jellyfin_url": "http://localhost:8096", "jellyfin_api_key": "abc"}
        )
    flow.async_step_tv_device.assert_called_once()
    assert result["step_id"] == "tv_device"


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
