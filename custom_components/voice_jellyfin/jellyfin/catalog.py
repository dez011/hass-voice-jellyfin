"""In-memory fuzzy-searchable catalog of Jellyfin media items."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .models import MediaItem

_LOGGER = logging.getLogger(__name__)

_MIN_SCORE = 0.5        # reject anything below this
_MIN_SCORE_GAP = 0.15  # top match must beat #2 by this much for short queries
_TRUSTED_SCORE = 0.9   # at or above this, a tie is real — never wipe the results

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
        _LOGGER.info(
            "Jellyfin catalog built: %d items indexed (%s)",
            len(self._entries),
            ", ".join(
                f"{t}={sum(1 for e in self._entries if e.item.type == t)}"
                for t in ("Movie", "Series")
            ),
        )

    def search(
        self,
        query: str,
        limit: int = 20,
        type_filter: "Optional[str]" = None,
        genre_hint: "Optional[str]" = None,
        year: "Optional[int]" = None,
    ) -> list["MediaItem"]:
        if not self._entries:
            return []
        query_lower = query.strip().lower()
        query_tokens = _tokenize(query_lower)

        # Empty query: meaningful only as a filter-browse ("a comedy from
        # 2019") — without filters it would otherwise match the whole library.
        if not query_lower:
            if not (type_filter or genre_hint or year):
                return []
            results = [
                e.item for e in self._entries
                if (not type_filter or e.item.type == type_filter)
                and (not year or e.item.year == year)
                and (not genre_hint or genre_hint in e.item.genres)
            ][:limit]
            return results

        scored: list[tuple[float, "MediaItem"]] = []
        for entry in self._entries:
            if type_filter and entry.item.type != type_filter:
                continue
            if year and entry.item.year != year:
                continue
            if genre_hint and genre_hint not in entry.item.genres:
                continue
            score = _score(query_lower, query_tokens, entry)
            if score >= _MIN_SCORE:
                scored.append((score, entry.item))
        scored.sort(key=lambda x: x[0], reverse=True)

        # For short queries (≤3 chars or single token) require the top hit to
        # clearly dominate the second — prevents "up" matching "Upside Down".
        #
        # Only low-confidence matches are wiped. Anything scoring >= _TRUSTED
        # matched whole words, so a tie there means several titles genuinely
        # start with what was asked for and all of them should come back.
        # Trusting only exact (1.0) matches meant a library holding both
        # "Bluey Espanol" and "Bluey - Espanol Canal Oficial" returned nothing
        # at all for "bluey": two whole-word prefix hits, zero gap, both wiped.
        short_query = len(query_lower.replace(" ", "")) <= 3 or len(query_tokens) <= 1
        if (
            short_query
            and len(scored) >= 2
            and scored[0][0] < _TRUSTED_SCORE
            and (scored[0][0] - scored[1][0]) < _MIN_SCORE_GAP
        ):
            scored = []

        results = [item for _, item in scored[:limit]]
        _LOGGER.debug(
            "Catalog search query=%r type=%s year=%s genre=%s → %d hits: %s",
            query, type_filter, year, genre_hint,
            len(results), [i.name for i in results[:5]],
        )
        return results

    @property
    def size(self) -> int:
        return len(self._entries)


def _score(query_lower: str, query_tokens: frozenset[str], entry: _Entry) -> float:
    name = entry.name_lower

    if query_lower == name:
        return 1.0

    # Query is a prefix of the title. Whether that is trustworthy depends on
    # whether it covers whole words: "bluey" is all of "Bluey Espanol"'s first
    # word, but "up" is only half of "Upside Down"'s. The first deserves to be
    # returned even when several titles tie; the second is the genuinely
    # ambiguous case _MIN_SCORE_GAP exists to suppress, so it scores lower and
    # stays subject to that guard.
    if name.startswith(query_lower):
        return 0.95 if not name[len(query_lower)].isalnum() else 0.8

    # "bluey espanol" matches "bluey" — title is a prefix of the query
    if query_lower.startswith(name):
        return 0.9

    # Substring, but only where the query starts on a word boundary. A raw
    # `in` check matched any mid-word run of letters — "hoe" is inside
    # "p(hoe)nix", so it pulled up Order of the Phoenix.
    if re.search(r"(?:^|\W)" + re.escape(query_lower), name):
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
