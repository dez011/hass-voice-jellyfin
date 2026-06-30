"""Voice query parsers — extract structured hints from raw command text."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class ParsedQuery:
    """Structured result of running raw text through the parser chain."""
    raw: str                          # original unmodified text
    query: str                        # cleaned text after parsers strip keywords
    type_filter: Optional[str] = None # "Movie" | "Series" | None
    genre_hint: Optional[str] = None  # e.g. "Comedy"
    year: Optional[int] = None


@runtime_checkable
class QueryParser(Protocol):
    """Interface every parser must implement."""
    def parse(self, result: ParsedQuery) -> ParsedQuery:
        """Mutate *result* in-place (or return a new one) and return it."""
        ...


# ---------------------------------------------------------------------------
# Concrete parsers
# ---------------------------------------------------------------------------

class TypeKeywordParser:
    """Strips type keywords and sets type_filter.

    Longest keywords are matched first so "tv show" beats "show".
    """

    # Maps spoken keyword → Jellyfin item type
    _KEYWORD_MAP: dict[str, str] = {
        # → Movie
        "movies":    "Movie",
        "movie":     "Movie",
        "films":     "Movie",
        "film":      "Movie",
        # → Series
        "tv shows":  "Series",
        "tv show":   "Series",
        "tv series": "Series",
        "tv":        "Series",
        "shows":     "Series",
        "show":      "Series",
        "series":    "Series",
        "anime":     "Series",
        "animes":    "Series",
        "cartoon":   "Series",
        "cartoons":  "Series",
        "episodes":  "Series",
        "episode":   "Series",
        "documentary": "Movie",
        "documentaries": "Movie",
    }

    # Compiled once at class level: longest keywords first to avoid partial matches
    _PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE), item_type)
        for kw, item_type in sorted(_KEYWORD_MAP.items(), key=lambda x: len(x[0]), reverse=True)
    ]

    def parse(self, result: ParsedQuery) -> ParsedQuery:
        for pattern, item_type in self._PATTERNS:
            if pattern.search(result.query):
                result.type_filter = item_type
                result.query = pattern.sub("", result.query).strip()
                # collapse multiple spaces
                result.query = re.sub(r"\s{2,}", " ", result.query)
                break
        return result


class YearParser:
    """Strips a 4-digit year and sets the year field."""

    _PATTERN = re.compile(r'\b(19[5-9]\d|20[0-4]\d)\b')

    def parse(self, result: ParsedQuery) -> ParsedQuery:
        m = self._PATTERN.search(result.query)
        if m:
            result.year = int(m.group())
            result.query = (result.query[:m.start()] + result.query[m.end():]).strip()
            result.query = re.sub(r"\s{2,}", " ", result.query)
        return result


class GenreKeywordParser:
    """Strips genre keywords and sets genre_hint."""

    _KEYWORD_MAP: dict[str, str] = {
        "action":    "Action",
        "comedy":    "Comedy",
        "comedies":  "Comedy",
        "horror":    "Horror",
        "thriller":  "Thriller",
        "romance":   "Romance",
        "romantic":  "Romance",
        "drama":     "Drama",
        "sci-fi":    "Science Fiction",
        "scifi":     "Science Fiction",
        "science fiction": "Science Fiction",
        "fantasy":   "Fantasy",
        "animation": "Animation",
        "animated":  "Animation",
        "documentary": "Documentary",
        "crime":     "Crime",
        "mystery":   "Mystery",
        "adventure": "Adventure",
        "family":    "Family",
    }

    _PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE), genre)
        for kw, genre in sorted(_KEYWORD_MAP.items(), key=lambda x: len(x[0]), reverse=True)
    ]

    def parse(self, result: ParsedQuery) -> ParsedQuery:
        for pattern, genre in self._PATTERNS:
            if pattern.search(result.query):
                result.genre_hint = genre
                result.query = pattern.sub("", result.query).strip()
                result.query = re.sub(r"\s{2,}", " ", result.query)
                break
        return result


# ---------------------------------------------------------------------------
# Registry — add new parsers here, order matters
# ---------------------------------------------------------------------------

PARSERS: list[QueryParser] = [
    TypeKeywordParser(),
    YearParser(),
    GenreKeywordParser(),
]


def parse_query(text: str) -> ParsedQuery:
    """Run *text* through all registered parsers and return a ParsedQuery."""
    result = ParsedQuery(raw=text, query=text.strip())
    for parser in PARSERS:
        result = parser.parse(result)
    return result
