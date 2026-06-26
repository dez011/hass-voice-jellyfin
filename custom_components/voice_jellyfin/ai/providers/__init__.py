"""Factory for AI provider instances."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ...const import (
    CONF_AI_PROVIDER,
    AI_PROVIDER_HA_CONVERSATION,
    AI_PROVIDER_OPENAI,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_GEMINI,
    AI_PROVIDER_OPENROUTER,
    AI_PROVIDER_OLLAMA,
    AI_PROVIDER_OPENAI_COMPAT,
    CONF_AI_API_KEY,
    CONF_AI_MODEL,
    CONF_AI_BASE_URL,
    CONF_AI_TEMPERATURE,
    CONF_AI_MAX_TOKENS,
    CONF_AI_STREAMING,
    CONF_AI_TIMEOUT,
    CONF_AI_ORG_ID,
    CONF_OLLAMA_HOST,
    CONF_OLLAMA_PORT,
    CONF_OLLAMA_HTTPS,
    CONF_OLLAMA_MODEL,
    CONF_OLLAMA_CONTEXT_SIZE,
    CONF_OLLAMA_KEEP_ALIVE,
    DEFAULT_AI_TEMPERATURE,
    DEFAULT_AI_MAX_TOKENS,
    DEFAULT_AI_TIMEOUT,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_PORT,
    DEFAULT_OLLAMA_CONTEXT_SIZE,
    DEFAULT_OLLAMA_KEEP_ALIVE,
)
from ..base import AIProvider

_LOGGER = logging.getLogger(__name__)


async def build_provider(hass: HomeAssistant, config: dict[str, Any]) -> AIProvider | None:
    """Instantiate and return the correct AIProvider from config data.

    Returns None if the provider cannot be loaded (missing optional dep, etc.).
    """
    provider_key = config.get(CONF_AI_PROVIDER, AI_PROVIDER_HA_CONVERSATION)

    if provider_key == AI_PROVIDER_HA_CONVERSATION:
        from .ha_conversation import HAConversationProvider
        return HAConversationProvider(hass)

    if provider_key == AI_PROVIDER_OLLAMA:
        from .ollama import OllamaProvider
        return OllamaProvider(
            host=config.get(CONF_OLLAMA_HOST, DEFAULT_OLLAMA_HOST),
            port=config.get(CONF_OLLAMA_PORT, DEFAULT_OLLAMA_PORT),
            https=config.get(CONF_OLLAMA_HTTPS, False),
            model=config.get(CONF_OLLAMA_MODEL, "llama3"),
            context_size=config.get(CONF_OLLAMA_CONTEXT_SIZE, DEFAULT_OLLAMA_CONTEXT_SIZE),
            keep_alive=config.get(CONF_OLLAMA_KEEP_ALIVE, DEFAULT_OLLAMA_KEEP_ALIVE),
            streaming=config.get(CONF_AI_STREAMING, True),
            timeout=config.get(CONF_AI_TIMEOUT, DEFAULT_AI_TIMEOUT),
        )

    if provider_key == AI_PROVIDER_OPENAI_COMPAT:
        from .openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(
            base_url=config.get(CONF_AI_BASE_URL, "http://localhost:1234/v1"),
            api_key=config.get(CONF_AI_API_KEY, "not-needed"),
            model=config.get(CONF_AI_MODEL, "local-model"),
            temperature=config.get(CONF_AI_TEMPERATURE, DEFAULT_AI_TEMPERATURE),
            max_tokens=config.get(CONF_AI_MAX_TOKENS, DEFAULT_AI_MAX_TOKENS),
            streaming=config.get(CONF_AI_STREAMING, True),
            timeout=config.get(CONF_AI_TIMEOUT, DEFAULT_AI_TIMEOUT),
        )

    if provider_key == AI_PROVIDER_OPENAI:
        from .openai import OpenAIProvider
        return OpenAIProvider(
            api_key=config[CONF_AI_API_KEY],
            model=config.get(CONF_AI_MODEL, "gpt-4o-mini"),
            temperature=config.get(CONF_AI_TEMPERATURE, DEFAULT_AI_TEMPERATURE),
            max_tokens=config.get(CONF_AI_MAX_TOKENS, DEFAULT_AI_MAX_TOKENS),
            timeout=config.get(CONF_AI_TIMEOUT, DEFAULT_AI_TIMEOUT),
            org_id=config.get(CONF_AI_ORG_ID),
        )

    if provider_key == AI_PROVIDER_ANTHROPIC:
        from .anthropic import AnthropicProvider
        return AnthropicProvider(
            api_key=config[CONF_AI_API_KEY],
            model=config.get(CONF_AI_MODEL, "claude-3-haiku-20240307"),
            max_tokens=config.get(CONF_AI_MAX_TOKENS, DEFAULT_AI_MAX_TOKENS),
            timeout=config.get(CONF_AI_TIMEOUT, DEFAULT_AI_TIMEOUT),
        )

    if provider_key == AI_PROVIDER_GEMINI:
        from .gemini import GeminiProvider
        return GeminiProvider(
            api_key=config[CONF_AI_API_KEY],
            model=config.get(CONF_AI_MODEL, "gemini-1.5-flash"),
            temperature=config.get(CONF_AI_TEMPERATURE, DEFAULT_AI_TEMPERATURE),
            max_tokens=config.get(CONF_AI_MAX_TOKENS, DEFAULT_AI_MAX_TOKENS),
        )

    if provider_key == AI_PROVIDER_OPENROUTER:
        from .openrouter import OpenRouterProvider
        return OpenRouterProvider(
            api_key=config[CONF_AI_API_KEY],
            model=config.get(CONF_AI_MODEL, "openai/gpt-4o-mini"),
            temperature=config.get(CONF_AI_TEMPERATURE, DEFAULT_AI_TEMPERATURE),
            max_tokens=config.get(CONF_AI_MAX_TOKENS, DEFAULT_AI_MAX_TOKENS),
            timeout=config.get(CONF_AI_TIMEOUT, DEFAULT_AI_TIMEOUT),
        )

    _LOGGER.error("Unknown AI provider: %s — falling back to HA Conversation", provider_key)
    from .ha_conversation import HAConversationProvider
    return HAConversationProvider(hass)
