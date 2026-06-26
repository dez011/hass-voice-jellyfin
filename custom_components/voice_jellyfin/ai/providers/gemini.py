"""Google Gemini provider using google-genai SDK."""
from __future__ import annotations

import logging
from typing import Optional

from ..base import AIProvider

_LOGGER = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    """Uses the google-genai SDK (AsyncClient)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client: Optional[object] = None

    @property
    def name(self) -> str:
        return f"Google Gemini ({self._model})"

    def _get_client(self) -> object:
        if self._client is None:
            from google import genai  # type: ignore[import]
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _build_prompt(self, messages: list[dict], system_prompt: str) -> str:
        parts = [f"SYSTEM:\n{system_prompt}\n"]
        for m in messages:
            role = m.get("role", "user").upper()
            parts.append(f"{role}:\n{m.get('content', '')}")
        return "\n\n".join(parts)

    async def async_query(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        from google import genai  # type: ignore[import]
        from google.genai import types  # type: ignore[import]

        client = self._get_client()
        prompt = self._build_prompt(messages, system_prompt)

        config = types.GenerateContentConfig(
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
        )

        response = await client.aio.models.generate_content(  # type: ignore[union-attr]
            model=self._model,
            contents=prompt,
            config=config,
        )
        return response.text.strip()
