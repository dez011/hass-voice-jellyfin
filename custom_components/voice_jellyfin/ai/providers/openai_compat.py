"""OpenAI-compatible provider for LM Studio, vLLM, and custom endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from ..base import AIProvider

_LOGGER = logging.getLogger(__name__)


class OpenAICompatProvider(AIProvider):
    """Uses the openai SDK with a custom base_url (LM Studio, vLLM, etc.)."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "not-needed",
        model: str = "local-model",
        temperature: float = 0.3,
        max_tokens: int = 512,
        streaming: bool = True,
        timeout: int = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._streaming = streaming
        self._timeout = timeout
        self._client: Optional[object] = None

    @property
    def name(self) -> str:
        return f"OpenAI-Compatible ({self._model})"

    def _get_client(self) -> object:
        if self._client is None:
            import openai  # type: ignore[import]
            self._client = openai.AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def async_query(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        client = self._get_client()
        api_messages = [{"role": "system", "content": system_prompt}] + list(messages)

        if self._streaming:
            content_parts: list[str] = []
            stream = await client.chat.completions.create(  # type: ignore[union-attr]
                model=self._model,
                messages=api_messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    content_parts.append(delta)
            return "".join(content_parts).strip()
        else:
            response = await client.chat.completions.create(  # type: ignore[union-attr]
                model=self._model,
                messages=api_messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
