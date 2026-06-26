"""Abstract base class for AI providers."""
from __future__ import annotations

from abc import ABC, abstractmethod


class AIProvider(ABC):
    """Interface that every AI provider must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this provider."""

    @abstractmethod
    async def async_query(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        """Send a conversation to the AI and return the text reply.

        :param messages: List of ``{"role": "user"|"assistant", "content": str}``
                         dicts representing the conversation history.
        :param system_prompt: System/instruction prompt prepended to every call.
        :returns: The model's text response.
        """
