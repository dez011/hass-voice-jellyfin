"""Google Gemini provider using google-generativeai."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..base import AIProvider

_LOGGER = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    """Wraps google.generativeai with async support via run_in_executor."""

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
        self._genai: Optional[object] = None

    @property
    def name(self) -> str:
        return f"Google Gemini ({self._model})"

    def _get_genai(self) -> object:
        if self._genai is None:
            import google.generativeai as genai  # type: ignore[import]
            genai.configure(api_key=self._api_key)
            self._genai = genai
        return self._genai

    def _build_prompt(self, messages: list[dict], system_prompt: str) -> str:
        """Flatten conversation into a single prompt string for Gemini."""
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
        genai = self._get_genai()
        prompt = self._build_prompt(messages, system_prompt)

        loop = asyncio.get_event_loop()

        def _sync_generate() -> str:
            model = genai.GenerativeModel(  # type: ignore[union-attr]
                self._model,
                generation_config={
                    "temperature": self._temperature,
                    "max_output_tokens": self._max_tokens,
                },
            )
            response = model.generate_content(prompt)
            return response.text.strip()

        return await loop.run_in_executor(None, _sync_generate)
