"""In-memory fuzzy-searchable catalog of Jellyfin media items."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MediaItem

_LOGGER = logging.getLogger(__name__)

_STOP_WORDS = frozenset({
    "the", "a", "an", "of", "and", "in", "on", "at", "to", "is", "s",
    "de", "la", "el", "en", "los", "las",  # common Spanish stop words
})


def _tokenize(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(w for w in words if w not in _STOP_WORDS and len(w) > 1)


@dataclass
class _Entry:
    item: "MediaItem"
    name_lower: str
    tokens: frozenset[str]


class JellyfinCatalog:
    """Local index for instant fuzzy matching against Jellyfin library."""

    def __init__(self) -> None:
        self._entries: list[_Entry] = []

    def build(self, items: list["MediaItem"]) -> None:
        self._entries = [
            _Entry(
                item=item,
                name_lower=item.name.lower(),
                tokens=_tokenize(item.name),
            )
            for item in items
        ]
        _LOGGER.warning(
            "Jellyfin catalog built: %d items indexed (%s)",
            len(self._entries),
            ", ".join(
                f"{t}={sum(1 for e in self._entries if e.item.type == t)}"
                for t in ("Movie", "Series")
            ),
        )

    def search(self, query: str, limit: int = 20) -> list["MediaItem"]:
        if not self._entries:
            return []
        query_lower = query.strip().lower()
        query_tokens = _tokenize(query_lower)
        scored: list[tuple[float, "MediaItem"]] = []
        for entry in self._entries:
            score = _score(query_lower, query_tokens, entry)
            if score > 0:
                scored.append((score, entry.item))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [item for _, item in scored[:limit]]
        _LOGGER.warning(
            "Catalog search query=%r → %d hits: %s",
            query,
            len(results),
            [i.name for i in results[:5]],
        )
        return results

    @property
    def size(self) -> int:
        return len(self._entries)


def _score(query_lower: str, query_tokens: frozenset[str], entry: _Entry) -> float:
    name = entry.name_lower

    if query_lower == name:
        return 1.0

    # "bluey" matches "bluey espanol" — query is a prefix of the title
    if name.startswith(query_lower):
        return 0.95

    # "bluey espanol" matches "bluey" — title is a prefix of the query
    if query_lower.startswith(name):
        return 0.9

    # substring anywhere
    if query_lower in name:
        return 0.85

    # token overlap (handles word-order differences, partial word matches)
    if not query_tokens or not entry.tokens:
        return 0.0
    overlap = len(query_tokens & entry.tokens)
    if overlap == 0:
        return 0.0
    recall = overlap / len(query_tokens)      # all query words found?
    precision = overlap / len(entry.tokens)   # how much of the title matched?
    return (recall * 0.7 + precision * 0.3) * 0.75
