"""Anthropic (Claude) provider."""
from __future__ import annotations

import logging
from typing import Optional

from ..base import AIProvider

_LOGGER = logging.getLogger(__name__)


class AnthropicProvider(AIProvider):
    """Uses the anthropic Python SDK (AsyncAnthropic)."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
        max_tokens: int = 512,
        timeout: int = 15,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._client: Optional[object] = None

    @property
    def name(self) -> str:
        return f"Anthropic ({self._model})"

    def _get_client(self) -> object:
        if self._client is None:
            import anthropic  # type: ignore[import]
            self._client = anthropic.AsyncAnthropic(
                api_key=self._api_key,
                timeout=float(self._timeout),
            )
        return self._client

    async def async_query(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        client = self._get_client()
        # Anthropic SDK expects user/assistant alternation; ensure we start with user
        api_messages = [m for m in messages if m.get("role") in ("user", "assistant")]
        # Drop leading assistant turns without adding a dummy user message to context history
        while api_messages and api_messages[0]["role"] != "user":
            api_messages = api_messages[1:]
        if not api_messages:
            api_messages = [{"role": "user", "content": "Hello"}]

        response = await client.messages.create(  # type: ignore[union-attr]
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=api_messages,
        )
        content = response.content[0].text if response.content else ""
        return content.strip()
