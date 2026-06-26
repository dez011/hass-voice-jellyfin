"""OpenAI chat completions provider."""
from __future__ import annotations

import logging
from typing import Optional

from ..base import AIProvider

_LOGGER = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    """Uses the official openai Python SDK (AsyncOpenAI)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
        max_tokens: int = 512,
        timeout: int = 15,
        org_id: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._org_id = org_id
        self._client: Optional[object] = None

    @property
    def name(self) -> str:
        return f"OpenAI ({self._model})"

    def _get_client(self) -> object:
        if self._client is None:
            import openai  # type: ignore[import]
            kwargs: dict = {"api_key": self._api_key, "timeout": self._timeout}
            if self._org_id:
                kwargs["organization"] = self._org_id
            self._client = openai.AsyncOpenAI(**kwargs)
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
