"""Conversation context / session memory for the AI layer."""
from __future__ import annotations

from typing import Any, Optional

from ..const import AI_CONTEXT_MAX_TURNS


class AIContext:
    """Holds a rolling conversation window and filter/navigation state.

    The context is per-config-entry and lives as long as the coordinator.
    It tracks:
      - up to ``max_turns`` of user/assistant turns
      - the currently-selected library
      - active filter criteria (genre, year, etc.)
      - the last executed action string
    """

    def __init__(self, max_turns: int = AI_CONTEXT_MAX_TURNS) -> None:
        self.max_turns = max_turns
        self.turns: list[dict[str, str]] = []
        self.current_library: Optional[str] = None
        self.current_filter: dict[str, Any] = {}
        self.last_action: Optional[str] = None

    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------

    def add_turn(self, role: str, content: str) -> None:
        """Append a turn and evict oldest pairs when over the limit.

        :param role: ``"user"`` or ``"assistant"``
        :param content: Text content of the turn.
        """
        self.turns.append({"role": role, "content": content})
        # Keep at most max_turns messages; drop from the front in pairs
        while len(self.turns) > self.max_turns * 2:
            self.turns.pop(0)
            self.turns.pop(0)

    def get_messages(self) -> list[dict[str, str]]:
        """Return the current conversation history suitable for the AI API."""
        return list(self.turns)

    def reset(self) -> None:
        """Clear all context state."""
        self.turns = []
        self.current_library = None
        self.current_filter = {}
        self.last_action = None
