"""AI provider backed by Home Assistant's built-in Conversation integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ..base import AIProvider

_LOGGER = logging.getLogger(__name__)


class HAConversationProvider(AIProvider):
    """Delegates queries to the HA Conversation service.

    The system prompt is prepended as the first user turn because the HA
    conversation service does not expose a dedicated system-prompt parameter.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    @property
    def name(self) -> str:
        return "Home Assistant Conversation"

    async def async_query(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        """Send the last user message to the HA conversation service.

        The system prompt is embedded into the text so the HA agent has
        context about the expected JSON response format.
        """
        # Extract the most recent user turn
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )

        # Combine system prompt with user text
        full_text = (
            f"{system_prompt}\n\nUser command: {last_user}"
        )

        try:
            result = await self._hass.services.async_call(
                "conversation",
                "process",
                {"text": full_text, "language": "en"},
                blocking=True,
                return_response=True,
            )
            # HA conversation returns {"response": {"speech": {"plain": {"speech": "..."}}}}
            response: Any = result or {}
            speech = (
                response.get("response", {})
                .get("speech", {})
                .get("plain", {})
                .get("speech", "")
            )
            return speech
        except Exception as exc:
            _LOGGER.error("HA Conversation service error: %s", exc)
            raise
