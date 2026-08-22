"""Tests for the in-memory JellyfinCatalog fuzzy search."""
from __future__ import annotations

import pytest

from custom_components.voice_jellyfin.jellyfin.catalog import JellyfinCatalog
from custom_components.voice_jellyfin.jellyfin.models import MediaItem


def _build(*items: MediaItem) -> JellyfinCatalog:
    catalog = JellyfinCatalog()
    catalog.build(list(items))
    return catalog


def test_exact_match_beats_prefix_sibling():
    """Regression: 'bluey' must match 'Bluey' even when 'Bluey Espanol' is
    only 0.05 behind — exact matches are exempt from the ambiguity gap rule."""
    catalog = _build(
        MediaItem(id="1", name="Bluey", type="Series"),
        MediaItem(id="2", name="Bluey Espanol", type="Series"),
    )
    results = catalog.search("bluey")
    assert [r.name for r in results][:1] == ["Bluey"]


def test_duplicate_exact_titles_are_both_returned():
    """Same title in two libraries must not annihilate itself."""
    catalog = _build(
        MediaItem(id="1", name="Cars", type="Movie"),
        MediaItem(id="2", name="Cars", type="Movie"),
    )
    results = catalog.search("cars")
    assert len(results) == 2


def test_short_ambiguous_prefix_still_guarded():
    """Non-exact short queries with near-tied scores still return nothing.

    'up' only covers half of 'Upside'/'Uptown', so neither is a whole-word
    hit and the ambiguity guard should still suppress both.
    """
    catalog = _build(
        MediaItem(id="1", name="Upside Down", type="Movie"),
        MediaItem(id="2", name="Uptown Girl", type="Movie"),
    )
    assert catalog.search("up") == []


def test_whole_word_prefix_tie_returns_all_matches():
    """Regression: a library with two 'Bluey ...' titles returned NOTHING for
    'bluey'. Both scored 0.95 as prefix matches, so the gap was zero and the
    short-query guard — which only exempted exact (1.0) matches — wiped them.

    These are the real titles from the reported library.
    """
    catalog = _build(
        MediaItem(id="1", name="Bluey Español", type="Series", year=2018),
        MediaItem(id="2", name="Bluey - Español Canal Oficial", type="Series"),
    )
    names = [r.name for r in catalog.search("bluey")]
    assert len(names) == 2, f"expected both Bluey titles, got {names}"
    assert "Bluey Español" in names


def test_partial_word_prefix_scores_below_whole_word():
    """'up' cutting into 'Upside' must rank lower than 'bluey' covering the
    whole first word — that difference is what keeps the guard selective."""
    partial = _build(MediaItem(id="1", name="Upside Down", type="Movie"))
    whole = _build(MediaItem(id="1", name="Bluey Español", type="Series"))
    # A lone partial-word hit still clears _MIN_SCORE, so both return a result;
    # the distinction only matters when several titles tie.
    assert [r.name for r in partial.search("up")] == ["Upside Down"]
    assert [r.name for r in whole.search("bluey")] == ["Bluey Español"]


def test_substring_must_start_on_a_word_boundary():
    """Regression: 'hoe' matched 'Harry Potter and the Order of the Phoenix'
    because a raw `in` check finds it mid-word inside 'p(hoe)nix'."""
    catalog = _build(
        MediaItem(
            id="1",
            name="Harry Potter and the Order of the Phoenix",
            type="Movie",
        ),
    )
    assert catalog.search("hoe") == []


def test_word_boundary_substring_still_matches_real_words():
    """The boundary rule must not break legitimate mid-title word matches."""
    catalog = _build(
        MediaItem(id="1", name="Harry Potter and the Goblet of Fire", type="Movie"),
    )
    assert [r.name for r in catalog.search("goblet")] == [
        "Harry Potter and the Goblet of Fire"
    ]


def test_word_prefix_substring_still_matches():
    """'aveng' should still reach 'The Avengers' — the boundary check anchors
    the start of the query, not both ends, so word prefixes keep working."""
    catalog = _build(MediaItem(id="1", name="The Avengers", type="Movie"))
    assert [r.name for r in catalog.search("aveng")] == ["The Avengers"]


def test_empty_query_without_filters_matches_nothing():
    catalog = _build(MediaItem(id="1", name="Anything", type="Movie"))
    assert catalog.search("") == []
    assert catalog.search("   ") == []


def test_empty_query_with_filters_browses():
    catalog = _build(
        MediaItem(id="1", name="Old Comedy", type="Movie", year=1999, genres=["Comedy"]),
        MediaItem(id="2", name="New Comedy", type="Movie", year=2020, genres=["Comedy"]),
        MediaItem(id="3", name="New Drama", type="Movie", year=2020, genres=["Drama"]),
    )
    results = catalog.search("", genre_hint="Comedy", year=2020)
    assert [r.name for r in results] == ["New Comedy"]


def test_type_filter():
    catalog = _build(
        MediaItem(id="1", name="Dune", type="Movie"),
        MediaItem(id="2", name="Dune Prophecy", type="Series"),
    )
    results = catalog.search("dune", type_filter="Series")
    assert [r.name for r in results] == ["Dune Prophecy"]


def test_year_filter():
    catalog = _build(
        MediaItem(id="1", name="Dune", type="Movie", year=1984),
        MediaItem(id="2", name="Dune", type="Movie", year=2021),
    )
    results = catalog.search("dune", year=2021)
    assert len(results) == 1 and results[0].year == 2021


def test_token_overlap_handles_word_order():
    catalog = _build(MediaItem(id="1", name="The Grand Budapest Hotel", type="Movie"))
    results = catalog.search("budapest hotel grand")
    assert [r.name for r in results] == ["The Grand Budapest Hotel"]


def test_no_match_below_min_score():
    catalog = _build(MediaItem(id="1", name="Interstellar", type="Movie"))
    assert catalog.search("completely unrelated query") == []


def test_size_property():
    catalog = _build(
        MediaItem(id="1", name="A", type="Movie"),
        MediaItem(id="2", name="B", type="Series"),
    )
    assert catalog.size == 2
    assert JellyfinCatalog().size == 0
