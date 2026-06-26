"""OpenRouter provider — OpenAI-compatible API at openrouter.ai."""
from __future__ import annotations

import logging
from typing import Optional

from ..base import AIProvider

_LOGGER = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(AIProvider):
    """Uses the openai SDK pointed at OpenRouter's API endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o-mini",
        temperature: float = 0.3,
        max_tokens: int = 512,
        timeout: int = 15,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._client: Optional[object] = None

    @property
    def name(self) -> str:
        return f"OpenRouter ({self._model})"

    def _get_client(self) -> object:
        if self._client is None:
            import openai  # type: ignore[import]
            self._client = openai.AsyncOpenAI(
                api_key=self._api_key,
                base_url=_OPENROUTER_BASE_URL,
                timeout=self._timeout,
                default_headers={
                    "HTTP-Referer": "https://github.com/dez011/hacs-voice-jellyfin",
                    "X-Title": "Voice Jellyfin",
                },
            )
        return self._client

    async def async_query(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        client = self._get_client()
        api_messages = [{"role": "system", "content": system_prompt}] + list(messages)
        response = await client.chat.completions.create(  # type: ignore[union-attr]
            model=self._model,
            messages=api_messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        content = response.choices[0].message.content or ""
        return content.strip()
