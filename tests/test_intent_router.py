"""Tests for IntentRouter — AI intent parsing and action dispatch."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.voice_jellyfin.ai.context import AIContext
from custom_components.voice_jellyfin.ai.intent_router import IntentRouter, IntentResult
from custom_components.voice_jellyfin.jellyfin.models import MediaItem, PlaybackSession


def _make_router(jellyfin=None, tv=None, nav=None, hass=None):
    return IntentRouter(
        jellyfin=jellyfin or MagicMock(),
        tv=tv or MagicMock(),
        nav=nav or MagicMock(),
        hass=hass or MagicMock(),
    )


def _provider_returning(payload: dict):
    provider = MagicMock()
    provider.async_query = AsyncMock(return_value=json.dumps(payload))
    return provider


# ---------------------------------------------------------------------------
# PLAY intent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_play_intent_calls_async_play():
    """PLAY intent should search and then play the first result."""
    item = MediaItem(id="item-001", name="Inception", type="Movie")
    session = PlaybackSession(id="sess-001", user_id="user-001", item=item)

    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[item])
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_play = AsyncMock()

    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "PLAY", "params": {"query": "Inception"}, "speech": "Playing Inception."})
    context = AIContext()

    result = await router.async_route("play Inception", provider, context)

    jellyfin.async_play.assert_called_once_with("sess-001", "item-001")
    assert result.media_title == "Inception"
    assert result.intent == "PLAY"


@pytest.mark.asyncio
async def test_play_intent_no_results_returns_speech():
    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[])
    jellyfin.async_get_sessions = AsyncMock(return_value=[])

    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "PLAY", "params": {"query": "xyz123"}})
    context = AIContext()

    result = await router.async_route("play xyz123", provider, context)

    jellyfin.async_play.assert_not_called() if hasattr(jellyfin.async_play, "assert_not_called") else None
    assert "couldn't find" in result.speech_reply.lower() or result.speech_reply != ""


# ---------------------------------------------------------------------------
# SEARCH intent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_intent_calls_async_search():
    item = MediaItem(id="item-002", name="The Matrix", type="Movie")
    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[item])

    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "SEARCH", "params": {"query": "the matrix"}})
    context = AIContext()

    result = await router.async_route("search the matrix", provider, context)

    jellyfin.async_search.assert_called_once_with("the matrix", limit=10)
    assert result.intent == "SEARCH"
    assert "The Matrix" in result.speech_reply


# ---------------------------------------------------------------------------
# NAVIGATE intent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_navigate_intent_sends_tv_key():
    tv = MagicMock()
    tv.async_send_key = AsyncMock()

    router = _make_router(tv=tv)
    provider = _provider_returning({"intent": "NAVIGATE", "params": {"direction": "down"}})
    context = AIContext()

    result = await router.async_route("go down", provider, context)

    tv.async_send_key.assert_called_once_with("down")
    assert result.intent == "NAVIGATE"


@pytest.mark.asyncio
async def test_navigate_intent_no_tv_does_not_raise():
    """With no TV controller configured, NAVIGATE should not raise."""
    router = _make_router(tv=None)
    provider = _provider_returning({"intent": "NAVIGATE", "params": {"direction": "up"}})
    context = AIContext()

    result = await router.async_route("go up", provider, context)
    assert result.intent == "NAVIGATE"


# ---------------------------------------------------------------------------
# FILTER intent updates context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filter_intent_updates_context():
    router = _make_router()
    provider = _provider_returning({
        "intent": "FILTER",
        "params": {"genre": "Action", "library_id": "lib-001"},
    })
    context = AIContext()

    await router.async_route("show me action movies", provider, context)

    assert context.current_filter.get("genre") == "Action"
    assert context.current_library == "lib-001"


# ---------------------------------------------------------------------------
# RESUME intent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resume_intent_calls_jellyfin_resume():
    jellyfin = MagicMock()
    jellyfin.async_resume = AsyncMock(return_value="Breaking Bad S01E01")
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "user-001"

    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "RESUME", "params": {"user_id": "user-001"}})
    context = AIContext()

    result = await router.async_route("resume", provider, context)

    jellyfin.async_resume.assert_called_once_with("user-001")
    assert result.media_title == "Breaking Bad S01E01"


# ---------------------------------------------------------------------------
# Context turns management
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_records_turns():
    router = _make_router()
    provider = _provider_returning({"intent": "GO_HOME", "params": {}})
    context = AIContext()

    await router.async_route("go home", provider, context)

    assert len(context.turns) >= 2
    assert context.turns[0]["role"] == "user"
    assert context.turns[0]["content"] == "go home"
    assert context.turns[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Provider failure fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_failure_falls_back_to_search():
    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[])

    router = _make_router(jellyfin=jellyfin)
    provider = MagicMock()
    provider.async_query = AsyncMock(side_effect=RuntimeError("API down"))
    context = AIContext()

    result = await router.async_route("find batman", provider, context)

    assert result.intent == "SEARCH"
    assert result.speech_reply  # fallback speech exists; exact wording may vary
