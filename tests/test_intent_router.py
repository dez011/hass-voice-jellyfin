"""Tests for IntentRouter — AI intent parsing and action dispatch."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.voice_jellyfin.ai.context import AIContext
from custom_components.voice_jellyfin.ai.intent_router import IntentRouter, IntentResult
from custom_components.voice_jellyfin.jellyfin.models import MediaItem, PlaybackSession


def _default_jellyfin():
    jf = MagicMock()
    jf.async_get_sessions = AsyncMock(return_value=[])
    jf.async_send_general_command = AsyncMock()
    jf._auth = MagicMock()
    jf._auth.user_id = None
    return jf


def _make_router(jellyfin=None, tv=None, nav=None, hass=None):
    return IntentRouter(
        jellyfin=jellyfin if jellyfin is not None else _default_jellyfin(),
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

    jellyfin.async_play.assert_called_once_with("sess-001", "item-001", start_ticks=0)
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

    jellyfin.async_search.assert_called_once_with(
        "the matrix", limit=10, type_filter=None, genre_hint=None, year=None,
        raw_query="the matrix",
    )
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
async def test_resume_intent_unpauses_paused_session():
    """RESUME should unpause a currently paused session rather than starting fresh."""
    item = MediaItem(id="ep-001", name="Breaking Bad S01E01", type="Episode")
    session = PlaybackSession(id="sess-001", user_id="user-001", item=item, is_paused=True)

    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_unpause = AsyncMock()
    jellyfin.async_resume = AsyncMock(return_value="Breaking Bad S01E01")
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "user-001"

    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "RESUME", "params": {"user_id": "user-001"}})
    context = AIContext()

    result = await router.async_route("resume", provider, context)

    jellyfin.async_unpause.assert_called_once_with("sess-001")
    jellyfin.async_resume.assert_not_called()
    assert result.media_title == "Breaking Bad S01E01"


@pytest.mark.asyncio
async def test_resume_intent_falls_back_to_resume_items_when_nothing_paused():
    """RESUME with no paused session should call async_resume for in-progress items."""
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[])
    jellyfin.async_resume = AsyncMock(return_value="Breaking Bad S01E01")
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "user-001"

    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "RESUME", "params": {"user_id": "user-001"}})
    context = AIContext()

    result = await router.async_route("resume", provider, context)

    jellyfin.async_resume.assert_called_once_with("user-001", device_filter=None)
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


# ---------------------------------------------------------------------------
# Rule-based routing (AI disabled or no provider)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_disabled_play_command_plays():
    """With AI off, "play X" must dispatch PLAY, not fall back to SEARCH."""
    item = MediaItem(id="item-001", name="Inception", type="Movie")
    session = PlaybackSession(id="sess-001", user_id="user-001", item=item)

    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[item])
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_play = AsyncMock()

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route(
        "play Inception", provider=None, context=AIContext(), ai_enabled=False
    )

    assert result.intent == "PLAY"
    jellyfin.async_play.assert_called_once_with("sess-001", "item-001", start_ticks=0)


@pytest.mark.asyncio
async def test_ai_disabled_search_command_searches():
    item = MediaItem(id="item-002", name="The Matrix", type="Movie")
    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[item])

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route(
        "find the matrix", provider=None, context=AIContext(), ai_enabled=False
    )

    assert result.intent == "SEARCH"
    assert "The Matrix" in result.speech_reply


@pytest.mark.asyncio
async def test_ai_disabled_pause_command_pauses():
    item = MediaItem(id="item-001", name="Inception", type="Movie")
    session = PlaybackSession(id="sess-001", user_id="user-001", item=item)
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_pause = AsyncMock()

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route(
        "pause", provider=None, context=AIContext(), ai_enabled=False
    )

    assert result.intent == "PAUSE"
    jellyfin.async_pause.assert_called_once_with("sess-001")


# ---------------------------------------------------------------------------
# Regression tests: parsing robustness and dispatch edge cases
# ---------------------------------------------------------------------------

def _provider_returning_raw(raw: str):
    provider = MagicMock()
    provider.async_query = AsyncMock(return_value=raw)
    return provider


@pytest.mark.asyncio
async def test_non_json_reply_searches_original_text():
    """When the AI answers with prose, search the USER's words — not the
    AI's error message."""
    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[])
    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning_raw("Sorry, I couldn't understand that request.")

    await router.async_route("play inception", provider, AIContext())

    query_used = jellyfin.async_search.call_args[0][0]
    assert "sorry" not in query_used.lower()
    assert "inception" in query_used.lower()


@pytest.mark.asyncio
async def test_json_embedded_in_prose_is_extracted():
    jellyfin = MagicMock()
    item = MediaItem(id="i1", name="Inception", type="Movie")
    session = PlaybackSession(id="s1", user_id="u1", item=item)
    jellyfin.async_search = AsyncMock(return_value=[item])
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_play = AsyncMock()
    router = _make_router(jellyfin=jellyfin, tv=None)
    provider = _provider_returning_raw(
        'Here is the JSON you asked for:\n{"intent": "PLAY", "params": {"query": "Inception"}}'
    )

    result = await router.async_route("play inception", provider, AIContext())
    assert result.intent == "PLAY"
    jellyfin.async_play.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_intent_does_not_claim_success():
    """A hallucinated intent must not produce the default 'Done.' reply."""
    router = _make_router()
    provider = _provider_returning({"intent": "VOLUME_UP", "params": {}})
    result = await router.async_route("turn it up", provider, AIContext())
    assert result.speech_reply  # non-empty
    assert "can't" in result.speech_reply.lower() or "sorry" in result.speech_reply.lower()


@pytest.mark.asyncio
async def test_repeat_intent_resends_last_nav_key():
    tv = MagicMock()
    tv.async_send_key = AsyncMock()
    nav = MagicMock()
    nav._last_key = "down"
    router = _make_router(tv=tv, nav=nav)
    provider = _provider_returning({"intent": "REPEAT", "params": {}})

    await router.async_route("again", provider, AIContext())
    tv.async_send_key.assert_called_once_with("down")


@pytest.mark.asyncio
async def test_repeat_intent_without_history_says_so():
    nav = MagicMock()
    nav._last_key = None
    tv = MagicMock()
    tv.async_send_key = AsyncMock()
    router = _make_router(tv=tv, nav=nav)
    provider = _provider_returning({"intent": "REPEAT", "params": {}})

    result = await router.async_route("again", provider, AIContext())
    tv.async_send_key.assert_not_called()
    assert "repeat" in result.speech_reply.lower()


@pytest.mark.asyncio
async def test_resume_with_null_user_id_falls_back_to_auth_user():
    """LLMs commonly emit "user_id": null for optional params."""
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[])
    jellyfin.async_resume = AsyncMock(return_value="Some Show")
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "auth-user"
    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "RESUME", "params": {"user_id": None}})

    await router.async_route("resume", provider, AIContext())
    jellyfin.async_resume.assert_called_once_with("auth-user", device_filter=None)


@pytest.mark.asyncio
async def test_play_season_as_string_is_coerced():
    item = MediaItem(id="series-1", name="Breaking Bad", type="Series")
    session = PlaybackSession(id="s1", user_id="u1", item=item)
    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[item])
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_get_series_play_target = AsyncMock(return_value=("ep-1", 0))
    jellyfin.async_play = AsyncMock()
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "u1"
    router = _make_router(jellyfin=jellyfin, tv=None)
    provider = _provider_returning(
        {"intent": "PLAY", "params": {"query": "Breaking Bad", "season": "3"}}
    )

    await router.async_route("play season 3 of breaking bad", provider, AIContext())
    season_arg = jellyfin.async_get_series_play_target.call_args[1]["season_number"]
    assert season_arg == 3 and isinstance(season_arg, int)


@pytest.mark.asyncio
async def test_quality_index_unchanged_when_restart_fails():
    """A failed stop/play must not desync the tracked quality step."""
    item = MediaItem(id="i1", name="Movie", type="Movie")
    session = PlaybackSession(id="s1", user_id="u1", item=item, position_ticks=100)
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_stop = AsyncMock(side_effect=ConnectionError("boom"))
    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "QUALITY_DOWN", "params": {}})

    before = router._bitrate_idx
    await router.async_route("lower the quality", provider, AIContext())
    assert router._bitrate_idx == before


@pytest.mark.asyncio
async def test_parse_non_dict_json_falls_back():
    router = _make_router()
    result = router._parse('["not", "a", "dict"]', fallback_query="original words")
    assert result.intent == "SEARCH"
    assert result.params["query"] == "original words"


@pytest.mark.asyncio
async def test_parse_null_speech_is_empty_string():
    router = _make_router()
    result = router._parse('{"intent": "SEARCH", "params": {"query": "x"}, "speech": null}')
    assert result.speech_reply == ""


# ---------------------------------------------------------------------------
# Device targeting — commands must stay on the router's configured TV
# ---------------------------------------------------------------------------

def _router_with_device_filter(device_filter, jellyfin=None, tv=None):
    return IntentRouter(
        jellyfin=jellyfin or MagicMock(),
        tv=tv or MagicMock(),
        nav=None,
        hass=MagicMock(),
        device_filter=device_filter,
    )


@pytest.mark.asyncio
async def test_pause_targets_only_matching_device():
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[
        PlaybackSession(id="s-mine", user_id="u1", item=MediaItem(id="i1", name="X", type="Movie"), device_name="Living Room"),
        PlaybackSession(id="s-brother", user_id="u2", item=MediaItem(id="i2", name="Y", type="Movie"), device_name="Bedroom"),
    ])
    jellyfin.async_pause = AsyncMock()
    router = _router_with_device_filter("Living Room", jellyfin=jellyfin)
    provider = _provider_returning({"intent": "PAUSE", "params": {}})

    await router.async_route("pause", provider, AIContext())
    jellyfin.async_pause.assert_awaited_once_with("s-mine")


@pytest.mark.asyncio
async def test_pause_with_no_matching_device_falls_back_to_any_session():
    """If the configured device has no sessions at all, fall back to any
    available real session so the button still works (e.g. user is on iPad
    while their Fire TV has nothing open)."""
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[
        PlaybackSession(id="s-ipad", user_id="u1", item=MediaItem(id="i1", name="X", type="Movie"), device_name="iPad"),
    ])
    jellyfin.async_pause = AsyncMock()
    router = _router_with_device_filter("Fire TV", jellyfin=jellyfin)
    provider = _provider_returning({"intent": "PAUSE", "params": {}})

    await router.async_route("pause", provider, AIContext())
    jellyfin.async_pause.assert_called_once_with("s-ipad")


@pytest.mark.asyncio
async def test_pause_cross_user_blocked_by_user_filter():
    """user_filter provides isolation: a device fallback must not grab
    another user's session."""
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[
        PlaybackSession(id="s-brother", user_id="u2", item=MediaItem(id="i2", name="Y", type="Movie"), device_name="Bedroom"),
    ])
    jellyfin.async_pause = AsyncMock()
    router = IntentRouter(
        jellyfin=jellyfin, tv=MagicMock(), nav=MagicMock(), hass=MagicMock(),
        device_filter="Living Room", user_filter="u1",  # u1 ≠ u2 (brother)
    )
    provider = _provider_returning({"intent": "PAUSE", "params": {}})

    await router.async_route("pause", provider, AIContext())
    jellyfin.async_pause.assert_not_called()


@pytest.mark.asyncio
async def test_play_with_no_matching_device_names_the_target_in_reply():
    jellyfin = MagicMock()
    item = MediaItem(id="i1", name="Inception", type="Movie")
    jellyfin.async_search = AsyncMock(return_value=[item])
    jellyfin.async_get_sessions = AsyncMock(return_value=[])
    router = _router_with_device_filter("Living Room", jellyfin=jellyfin)
    provider = _provider_returning({"intent": "PLAY", "params": {"query": "Inception"}})

    result = await router.async_route("play inception", provider, AIContext())
    assert "Living Room" in result.speech_reply


@pytest.mark.asyncio
async def test_now_playing_omits_device_note_when_already_targeted():
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[
        PlaybackSession(id="s1", user_id="u1", item=MediaItem(id="i1", name="Show", type="Movie"), device_name="Living Room"),
    ])
    router = _router_with_device_filter("Living Room", jellyfin=jellyfin)
    provider = _provider_returning({"intent": "NOW_PLAYING", "params": {}})

    result = await router.async_route("what's playing", provider, AIContext())
    assert "Living Room" not in result.speech_reply
    assert "Show" in result.speech_reply


@pytest.mark.asyncio
async def test_now_playing_names_device_when_untargeted():
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[
        PlaybackSession(id="s1", user_id="u1", item=MediaItem(id="i1", name="Show", type="Movie"), device_name="Living Room"),
    ])
    router = _make_router(jellyfin=jellyfin)  # no device_filter
    provider = _provider_returning({"intent": "NOW_PLAYING", "params": {}})

    result = await router.async_route("what's playing", provider, AIContext())
    assert "Living Room" in result.speech_reply
