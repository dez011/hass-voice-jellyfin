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


# ---------------------------------------------------------------------------
# Factory: missing API key and model defaults
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_provider_cloud_without_api_key_returns_none(mock_hass):
    """A cloud provider without an API key must degrade to None (rule-based
    intents), not raise KeyError during setup."""
    from custom_components.voice_jellyfin.ai.providers import build_provider

    for key in ("openai", "anthropic", "gemini", "openrouter"):
        provider = await build_provider(mock_hass, {"ai_provider": key})
        assert provider is None, f"{key} should return None without an API key"


@pytest.mark.asyncio
async def test_build_provider_anthropic_default_model_is_current(mock_hass):
    """Regression: the default was the retired claude-3-haiku-20240307."""
    from custom_components.voice_jellyfin.ai.providers import build_provider

    provider = await build_provider(
        mock_hass, {"ai_provider": "anthropic", "ai_api_key": "sk-test"}
    )
    assert provider is not None
    assert "claude-3-" not in provider.name
    assert "claude-haiku-4-5" in provider.name


@pytest.mark.asyncio
async def test_build_provider_empty_model_string_uses_default(mock_hass):
    """An empty ai_model saved by the options flow must not become the model."""
    from custom_components.voice_jellyfin.ai.providers import build_provider

    provider = await build_provider(
        mock_hass, {"ai_provider": "openai", "ai_api_key": "sk-test", "ai_model": ""}
    )
    assert "gpt-4o-mini" in provider.name


# ---------------------------------------------------------------------------
# Ollama error chunks
# ---------------------------------------------------------------------------

def _ollama_mock_session(mock_resp):
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(return_value=mock_resp)
    return mock_session


@pytest.mark.asyncio
async def test_ollama_streaming_error_chunk_raises():
    """Ollama reports mid-stream failures (e.g. OOM) as an error chunk with
    HTTP 200 — swallowing it produced a silent empty reply."""
    from custom_components.voice_jellyfin.ai.providers.ollama import OllamaProvider

    provider = OllamaProvider(streaming=True, timeout=5)
    lines = [
        json.dumps({"message": {"content": "partial"}}).encode(),
        json.dumps({"error": "model ran out of memory"}).encode(),
    ]

    async def _aiter():
        for line in lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = _aiter()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=_ollama_mock_session(mock_resp)):
        with pytest.raises(RuntimeError, match="out of memory"):
            await provider.async_query([{"role": "user", "content": "hi"}], "")


@pytest.mark.asyncio
async def test_ollama_non_streaming_error_raises():
    from custom_components.voice_jellyfin.ai.providers.ollama import OllamaProvider

    provider = OllamaProvider(streaming=False, timeout=5)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={"error": "model not found"})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=_ollama_mock_session(mock_resp)):
        with pytest.raises(RuntimeError, match="model not found"):
            await provider.async_query([{"role": "user", "content": "hi"}], "")


# ---------------------------------------------------------------------------
# OpenAI reasoning-model parameter switching (SDK mocked via sys.modules)
# ---------------------------------------------------------------------------

def _install_fake_openai(captured: dict):
    import sys, types

    fake = types.ModuleType("openai")

    class _AsyncOpenAI:
        def __init__(self, **kwargs):
            self.chat = MagicMock()

            async def _create(**call_kwargs):
                captured.update(call_kwargs)
                resp = MagicMock()
                resp.choices = [MagicMock()]
                resp.choices[0].message.content = '{"intent":"SEARCH","params":{}}'
                return resp

            self.chat.completions.create = _create

    fake.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = fake
    return fake


@pytest.mark.asyncio
async def test_openai_reasoning_model_uses_max_completion_tokens():
    import sys
    from custom_components.voice_jellyfin.ai.providers.openai import OpenAIProvider

    captured: dict = {}
    _install_fake_openai(captured)
    try:
        provider = OpenAIProvider(api_key="sk", model="o4-mini", max_tokens=256)
        await provider.async_query([{"role": "user", "content": "hi"}], "sys")
        assert captured["max_completion_tokens"] == 256
        assert "max_tokens" not in captured
        assert "temperature" not in captured
    finally:
        sys.modules.pop("openai", None)


@pytest.mark.asyncio
async def test_openai_classic_model_uses_max_tokens():
    import sys
    from custom_components.voice_jellyfin.ai.providers.openai import OpenAIProvider

    captured: dict = {}
    _install_fake_openai(captured)
    try:
        provider = OpenAIProvider(api_key="sk", model="gpt-4o-mini", max_tokens=256, temperature=0.3)
        await provider.async_query([{"role": "user", "content": "hi"}], "sys")
        assert captured["max_tokens"] == 256
        assert captured["temperature"] == 0.3
        assert "max_completion_tokens" not in captured
    finally:
        sys.modules.pop("openai", None)


# ---------------------------------------------------------------------------
# Anthropic content-block handling (SDK mocked via sys.modules)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anthropic_skips_leading_non_text_blocks():
    import sys, types
    from custom_components.voice_jellyfin.ai.providers.anthropic import AnthropicProvider

    thinking_block = MagicMock(spec=[])  # no .text attribute
    text_block = MagicMock()
    text_block.text = '{"intent":"SEARCH","params":{}}'

    fake = types.ModuleType("anthropic")

    class _AsyncAnthropic:
        def __init__(self, **kwargs):
            resp = MagicMock()
            resp.content = [thinking_block, text_block]
            self.messages = MagicMock()
            self.messages.create = AsyncMock(return_value=resp)

    fake.AsyncAnthropic = _AsyncAnthropic
    sys.modules["anthropic"] = fake
    try:
        provider = AnthropicProvider(api_key="sk")
        result = await provider.async_query([{"role": "user", "content": "hi"}], "sys")
        assert "SEARCH" in result
    finally:
        sys.modules.pop("anthropic", None)


@pytest.mark.asyncio
async def test_anthropic_drops_leading_assistant_turns():
    import sys, types
    from custom_components.voice_jellyfin.ai.providers.anthropic import AnthropicProvider

    captured: dict = {}
    fake = types.ModuleType("anthropic")

    class _AsyncAnthropic:
        def __init__(self, **kwargs):
            async def _create(**call_kwargs):
                captured.update(call_kwargs)
                resp = MagicMock()
                block = MagicMock()
                block.text = "{}"
                resp.content = [block]
                return resp

            self.messages = MagicMock()
            self.messages.create = _create

    fake.AsyncAnthropic = _AsyncAnthropic
    sys.modules["anthropic"] = fake
    try:
        provider = AnthropicProvider(api_key="sk")
        await provider.async_query(
            [
                {"role": "assistant", "content": "stale reply"},
                {"role": "user", "content": "hi"},
            ],
            "sys",
        )
        assert captured["messages"][0]["role"] == "user"
    finally:
        sys.modules.pop("anthropic", None)


# ---------------------------------------------------------------------------
# HA Conversation provider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ha_conversation_uses_instance_language(mock_hass):
    from custom_components.voice_jellyfin.ai.providers.ha_conversation import HAConversationProvider

    mock_hass.config.language = "de"
    mock_hass.services.async_call = AsyncMock(
        return_value={"response": {"speech": {"plain": {"speech": "ok"}}}}
    )
    provider = HAConversationProvider(mock_hass)
    result = await provider.async_query([{"role": "user", "content": "hallo"}], "sys")
    assert result == "ok"
    service_data = mock_hass.services.async_call.call_args[0][2]
    assert service_data["language"] == "de"
