"""Tests for AI provider implementations and the factory."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ollama_provider_async_query_non_streaming():
    """OllamaProvider returns the message content from a non-streaming response."""
    from custom_components.voice_jellyfin.ai.providers.ollama import OllamaProvider

    provider = OllamaProvider(
        host="localhost", port=11434, model="llama3", streaming=False, timeout=10
    )

    payload = {"message": {"role": "assistant", "content": '{"intent":"PLAY","params":{"query":"Inception"},"speech":"Playing Inception."}'}, "done": True}

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=payload)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(return_value=mock_resp)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await provider.async_query(
            messages=[{"role": "user", "content": "play Inception"}],
            system_prompt="You are a media controller.",
        )

    assert "PLAY" in result
    data = json.loads(result)
    assert data["params"]["query"] == "Inception"


@pytest.mark.asyncio
async def test_ollama_provider_async_query_streaming():
    """OllamaProvider concatenates streaming chunks."""
    from custom_components.voice_jellyfin.ai.providers.ollama import OllamaProvider

    provider = OllamaProvider(
        host="localhost", port=11434, model="llama3", streaming=True, timeout=10
    )

    # Simulate NDJSON lines
    chunks = [
        json.dumps({"message": {"content": '{"intent":'}}),
        json.dumps({"message": {"content": '"SEARCH",'}}),
        json.dumps({"message": {"content": '"params":{"query":"batman"}}'}}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]
    raw_lines = [c.encode() for c in chunks]

    async def _aiter_lines():
        for line in raw_lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = _aiter_lines()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(return_value=mock_resp)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await provider.async_query(
            messages=[{"role": "user", "content": "find batman"}],
            system_prompt="",
        )

    assert "SEARCH" in result


@pytest.mark.asyncio
async def test_ollama_list_models():
    """async_list_models returns model name strings from the API response."""
    from custom_components.voice_jellyfin.ai.providers.ollama import OllamaProvider

    payload = {
        "models": [
            {"name": "llama3", "size": 4000000000},
            {"name": "mistral", "size": 3500000000},
        ]
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=payload)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = MagicMock(return_value=mock_resp)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        models = await OllamaProvider.async_list_models("localhost", 11434, False)

    assert models == ["llama3", "mistral"]


# ---------------------------------------------------------------------------
# build_provider factory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_provider_ollama(mock_hass):
    """build_provider returns OllamaProvider when ai_provider == 'ollama'."""
    from custom_components.voice_jellyfin.ai.providers import build_provider
    from custom_components.voice_jellyfin.ai.providers.ollama import OllamaProvider

    config = {
        "ai_provider": "ollama",
        "ollama_host": "localhost",
        "ollama_port": 11434,
        "ollama_https": False,
        "ollama_model": "llama3",
    }
    provider = await build_provider(mock_hass, config)
    assert isinstance(provider, OllamaProvider)
    assert "llama3" in provider.name


@pytest.mark.asyncio
async def test_build_provider_ha_conversation(mock_hass):
    """build_provider returns HAConversationProvider for ha_conversation key."""
    from custom_components.voice_jellyfin.ai.providers import build_provider
    from custom_components.voice_jellyfin.ai.providers.ha_conversation import HAConversationProvider

    config = {"ai_provider": "ha_conversation"}
    provider = await build_provider(mock_hass, config)
    assert isinstance(provider, HAConversationProvider)


@pytest.mark.asyncio
async def test_build_provider_openai_compat(mock_hass):
    """build_provider returns OpenAICompatProvider for openai_compat key."""
    from custom_components.voice_jellyfin.ai.providers import build_provider
    from custom_components.voice_jellyfin.ai.providers.openai_compat import OpenAICompatProvider

    config = {
        "ai_provider": "openai_compat",
        "ai_base_url": "http://localhost:1234/v1",
        "ai_api_key": "not-needed",
        "ai_model": "local-model",
    }
    provider = await build_provider(mock_hass, config)
    assert isinstance(provider, OpenAICompatProvider)


@pytest.mark.asyncio
async def test_build_provider_unknown_falls_back(mock_hass):
    """Unknown provider key falls back to HAConversationProvider."""
    from custom_components.voice_jellyfin.ai.providers import build_provider
    from custom_components.voice_jellyfin.ai.providers.ha_conversation import HAConversationProvider

    config = {"ai_provider": "totally_unknown_provider_xyz"}
    provider = await build_provider(mock_hass, config)
    assert isinstance(provider, HAConversationProvider)
