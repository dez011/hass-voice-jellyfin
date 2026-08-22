"""Tests for the voice query parser chain."""
from __future__ import annotations

from custom_components.voice_jellyfin.jellyfin.query_parser import parse_query


def test_plain_query_untouched():
    pq = parse_query("the dark knight")
    assert pq.query == "the dark knight"
    assert pq.type_filter is None
    assert pq.genre_hint is None
    assert pq.year is None


def test_type_keyword_movie():
    pq = parse_query("batman movie")
    assert pq.type_filter == "Movie"
    assert pq.query == "batman"


def test_type_keyword_tv_show_beats_show():
    pq = parse_query("some tv show about cars")
    assert pq.type_filter == "Series"
    assert "tv show" not in pq.query


def test_year_extracted():
    pq = parse_query("dune 2021")
    assert pq.year == 2021
    assert pq.query == "dune"


def test_year_titled_movie_not_stripped():
    """Regression: 'play 2012' — the number IS the title; stripping it left
    an empty query that matched the entire catalog (or nothing)."""
    pq = parse_query("2012")
    assert pq.query == "2012"
    assert pq.year is None


def test_year_titled_movie_1917():
    pq = parse_query("1917")
    assert pq.query == "1917"
    assert pq.year is None


def test_genre_keyword():
    pq = parse_query("something funny comedy")
    assert pq.genre_hint == "Comedy"
    assert "comedy" not in pq.query


def test_combined_type_year_genre():
    pq = parse_query("action movie from 2010")
    assert pq.type_filter == "Movie"
    assert pq.year == 2010
    assert pq.genre_hint == "Action"


def test_raw_preserved():
    pq = parse_query("comedy movie 1999")
    assert pq.raw == "comedy movie 1999"
