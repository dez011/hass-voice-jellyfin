"""Tests for new voice intents: NEXT_EPISODE, SKIP_INTRO, QUALITY, FAVORITE, NOW_PLAYING, OPEN_APP, PLAY_LATEST, season play."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import inspect

import pytest

from custom_components.voice_jellyfin.ai.context import AIContext
from custom_components.voice_jellyfin.ai.intent_router import IntentRouter, IntentResult
from custom_components.voice_jellyfin.jellyfin.models import MediaItem, PlaybackSession
from custom_components.voice_jellyfin.jellyfin.auth import JellyfinAuth
from custom_components.voice_jellyfin.jellyfin.client import JellyfinClient


def _make_router(jellyfin=None, tv=None, nav=None, hass=None, **kw):
    return IntentRouter(
        jellyfin=jellyfin or MagicMock(),
        tv=tv or MagicMock(),
        nav=nav or MagicMock(),
        hass=hass or MagicMock(),
        **kw,
    )


def _provider_returning(payload: dict):
    p = MagicMock()
    p.async_query = AsyncMock(return_value=json.dumps(payload))
    return p


def _playing_session(item_name="Bluey", item_id="item-001", paused=False, position=0):
    item = MediaItem(id=item_id, name=item_name, type="Episode")
    return PlaybackSession(id="sess-001", user_id="user-001", item=item, is_paused=paused, position_ticks=position)


# ---------------------------------------------------------------------------
# NEXT_EPISODE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_next_episode_calls_next_track():
    session = _playing_session()
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_next_track = AsyncMock()

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route("next episode", provider=None, context=AIContext(), ai_enabled=False)

    jellyfin.async_next_track.assert_called_once_with("sess-001")
    assert result.intent == "NEXT_EPISODE"


@pytest.mark.asyncio
async def test_next_episode_nothing_playing():
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[])
    jellyfin.async_next_track = AsyncMock()

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route("next episode", provider=None, context=AIContext(), ai_enabled=False)

    jellyfin.async_next_track.assert_not_called()
    assert "nothing" in result.speech_reply.lower()


# ---------------------------------------------------------------------------
# SKIP_INTRO
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_intro_called():
    session = _playing_session(position=10_000_000)
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_skip_intro = AsyncMock(return_value=True)

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route("skip intro", provider=None, context=AIContext(), ai_enabled=False)

    jellyfin.async_skip_intro.assert_called_once_with("sess-001")
    assert result.intent == "SKIP_INTRO"


# ---------------------------------------------------------------------------
# QUALITY_DOWN / QUALITY_UP
# ---------------------------------------------------------------------------

_PRESETS = [500, 2000, 8000]


def _quality_jellyfin(session=None, current_kbps=0, set_ok=True):
    """Jellyfin double wired for the bitrate-cap path."""
    jf = MagicMock()
    jf._auth = MagicMock()
    jf._auth.user_id = "user-001"
    jf.async_get_sessions = AsyncMock(return_value=[session] if session else [])
    jf.async_get_bitrate_limit = AsyncMock(return_value=current_kbps)
    jf.async_set_bitrate_limit = AsyncMock(return_value=set_ok)
    jf.async_send_general_command = AsyncMock(return_value=True)
    jf.async_stop = AsyncMock()
    jf.async_play = AsyncMock()
    return jf


async def _route(jellyfin, text, presets=None):
    router = _make_router(jellyfin=jellyfin, bitrate_presets=presets or _PRESETS)
    return await router.async_route(text, provider=None, context=AIContext(), ai_enabled=False)


@pytest.mark.asyncio
async def test_quality_down_from_uncapped_caps_at_top_preset():
    session = _playing_session(position=5_000_000)
    jellyfin = _quality_jellyfin(session, current_kbps=0)

    result = await _route(jellyfin, "lower quality")

    assert result.intent == "QUALITY_DOWN"
    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 8000)
    # The running stream keeps its original bitrate, so it is restarted in place.
    jellyfin.async_stop.assert_awaited_once_with("sess-001")
    jellyfin.async_play.assert_awaited_once_with("sess-001", "item-001", start_ticks=5_000_000)


@pytest.mark.asyncio
async def test_quality_down_steps_to_next_lower_preset():
    session = _playing_session(position=1_000_000)
    jellyfin = _quality_jellyfin(session, current_kbps=2000)

    await _route(jellyfin, "lower quality")

    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 500)


@pytest.mark.asyncio
async def test_quality_down_at_the_bottom_says_so_without_reapplying():
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=500)

    result = await _route(jellyfin, "lower quality")

    jellyfin.async_set_bitrate_limit.assert_not_awaited()
    assert "lowest" in result.speech_reply.lower()


@pytest.mark.asyncio
async def test_quality_up_steps_to_next_higher_preset():
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=500)

    await _route(jellyfin, "higher quality")

    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 2000)


@pytest.mark.asyncio
async def test_quality_up_at_the_top_says_so_without_reapplying():
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=8000)

    result = await _route(jellyfin, "higher quality")

    # The scale has a top; removing the cap needs an explicit "auto".
    jellyfin.async_set_bitrate_limit.assert_not_awaited()
    assert "highest" in result.speech_reply.lower()


@pytest.mark.asyncio
async def test_quality_up_when_already_uncapped_does_nothing():
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=0)

    result = await _route(jellyfin, "higher quality")

    jellyfin.async_set_bitrate_limit.assert_not_awaited()
    assert "unlimited" in result.speech_reply.lower()


@pytest.mark.asyncio
async def test_set_quality_named_level():
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=0)

    result = await _route(jellyfin, "set the quality to low")

    assert result.intent == "SET_QUALITY"
    # "low" is an alias for level 2 on the 1-5 scale.
    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 4000)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase,expected_kbps",
    [
        ("cap the bitrate at 3 mbps", 3000),
        ("set the bitrate to 1500 kbps", 1500),
        ("limit the quality to 2 megabits", 2000),
    ],
)
async def test_set_quality_explicit_bitrate(phrase, expected_kbps):
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=0)

    await _route(jellyfin, phrase)

    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", expected_kbps)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase", ["remove the quality limit", "reset the quality", "set quality to auto"]
)
async def test_set_quality_auto_removes_the_cap(phrase):
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=2000)

    await _route(jellyfin, phrase)

    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 0)


@pytest.mark.asyncio
async def test_set_quality_with_nothing_playing_still_applies():
    jellyfin = _quality_jellyfin(session=None, current_kbps=0)

    result = await _route(jellyfin, "set the quality to low")

    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 4000)
    jellyfin.async_play.assert_not_awaited()
    assert "next thing you play" in result.speech_reply


@pytest.mark.asyncio
async def test_set_quality_without_admin_rights_explains_why():
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=0, set_ok=False)

    result = await _route(jellyfin, "set the quality to low")

    # Nothing is restarted when the cap could not be written.
    jellyfin.async_stop.assert_not_awaited()
    jellyfin.async_play.assert_not_awaited()
    assert "administrator" in result.speech_reply.lower()


@pytest.mark.asyncio
async def test_quality_status_reports_the_current_cap():
    jellyfin = _quality_jellyfin(session=None, current_kbps=4000)

    result = await _route(jellyfin, "what's the bitrate")

    assert result.intent == "QUALITY_STATUS"
    assert "4 megabits" in result.speech_reply
    jellyfin.async_set_bitrate_limit.assert_not_awaited()


@pytest.mark.asyncio
async def test_buffering_complaint_lowers_quality():
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=8000)

    result = await _route(jellyfin, "it keeps buffering")

    assert result.intent == "QUALITY_DOWN"
    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 2000)


# ---------------------------------------------------------------------------
# FAVORITE / UNFAVORITE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_favorite_adds_to_favorites():
    session = _playing_session()
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_set_favorite = AsyncMock()
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "user-001"

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route("add to favorites", provider=None, context=AIContext(), ai_enabled=False)

    jellyfin.async_set_favorite.assert_called_once_with("user-001", "item-001", is_favorite=True)
    assert result.intent == "FAVORITE"


@pytest.mark.asyncio
async def test_unfavorite_removes_from_favorites():
    session = _playing_session()
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_set_favorite = AsyncMock()
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "user-001"

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route("remove from favorites", provider=None, context=AIContext(), ai_enabled=False)

    jellyfin.async_set_favorite.assert_called_once_with("user-001", "item-001", is_favorite=False)
    assert result.intent == "UNFAVORITE"


@pytest.mark.asyncio
async def test_favorite_nothing_playing_returns_speech():
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[])
    jellyfin.async_set_favorite = AsyncMock()
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "user-001"

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route("add to favorites", provider=None, context=AIContext(), ai_enabled=False)

    jellyfin.async_set_favorite.assert_not_called()
    assert result.speech_reply


# ---------------------------------------------------------------------------
# NOW_PLAYING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_now_playing_returns_title():
    session = _playing_session("Interstellar")
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route("what's playing", provider=None, context=AIContext(), ai_enabled=False)

    assert result.intent == "NOW_PLAYING"
    assert "Interstellar" in result.speech_reply


@pytest.mark.asyncio
async def test_now_playing_nothing_returns_speech():
    jellyfin = MagicMock()
    jellyfin.async_get_sessions = AsyncMock(return_value=[])

    router = _make_router(jellyfin=jellyfin)
    result = await router.async_route("what's playing", provider=None, context=AIContext(), ai_enabled=False)

    assert "nothing" in result.speech_reply.lower()


# ---------------------------------------------------------------------------
# OPEN_APP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_app_wakes_and_launches():
    async def _fake_ensure_awake():
        return True

    tv = MagicMock()
    tv.async_ensure_awake = _fake_ensure_awake
    tv.async_launch_app = AsyncMock(return_value=True)

    router = _make_router(tv=tv, preferred_client_package="org.jellyfin.androidtv")
    result = await router.async_route("open jellyfin", provider=None, context=AIContext(), ai_enabled=False)

    tv.async_launch_app.assert_called_once_with("org.jellyfin.androidtv")
    assert result.intent == "OPEN_APP"
    assert "jellyfin" in result.speech_reply.lower()


@pytest.mark.asyncio
async def test_open_app_no_tv_configured():
    router = IntentRouter(
        jellyfin=MagicMock(), tv=None, nav=MagicMock(), hass=MagicMock()
    )
    result = await router.async_route("open jellyfin", provider=None, context=AIContext(), ai_enabled=False)

    assert "no tv" in result.speech_reply.lower()


# ---------------------------------------------------------------------------
# PLAY with season
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_play_season_passes_season_number():
    series = MediaItem(id="series-001", name="Breaking Bad", type="Series")
    ep = MediaItem(id="ep-s3e1", name="No Más", type="Episode")
    session = PlaybackSession(id="sess-001", user_id="user-001", item=None)

    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[series])
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_get_series_play_target = AsyncMock(return_value=("ep-s3e1", 0))
    jellyfin.async_play = AsyncMock()
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "user-001"

    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "PLAY", "params": {"query": "Breaking Bad", "season": 3}})
    result = await router.async_route("play season 3 of breaking bad", provider, AIContext())

    jellyfin.async_get_series_play_target.assert_called_once_with("series-001", "user-001", season_number=3)
    jellyfin.async_play.assert_called_once_with("sess-001", "ep-s3e1", start_ticks=0)
    assert "season 3" in result.speech_reply.lower()


# ---------------------------------------------------------------------------
# PLAY_LATEST
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_play_latest_plays_newest_episode():
    series = MediaItem(id="series-001", name="Bluey", type="Series")
    session = _playing_session()

    jellyfin = MagicMock()
    jellyfin.async_search = AsyncMock(return_value=[series])
    jellyfin.async_get_latest_episode = AsyncMock(return_value=("ep-latest", "Camping"))
    jellyfin.async_get_sessions = AsyncMock(return_value=[session])
    jellyfin.async_play = AsyncMock()
    jellyfin._auth = MagicMock()
    jellyfin._auth.user_id = "user-001"

    router = _make_router(jellyfin=jellyfin)
    provider = _provider_returning({"intent": "PLAY_LATEST", "params": {"query": "Bluey"}})
    result = await router.async_route("play latest episode of bluey", provider, AIContext())

    jellyfin.async_get_latest_episode.assert_called_once_with("series-001", "user-001")
    jellyfin.async_play.assert_called_once_with("sess-001", "ep-latest")
    assert "Camping" in result.speech_reply


# ---------------------------------------------------------------------------
# Catalog min-score threshold
# ---------------------------------------------------------------------------

def test_catalog_min_score_rejects_low_confidence():
    from custom_components.voice_jellyfin.jellyfin.catalog import JellyfinCatalog
    catalog = JellyfinCatalog()
    catalog.build([
        MediaItem(id="m1", name="Up", type="Movie"),
        MediaItem(id="m2", name="Uptown Funk Documentary", type="Movie"),
    ])
    # "Up" is 2 chars — both items could match; gap is too small, should return []
    results = catalog.search("up", limit=5)
    assert results == [], f"Expected no results for ambiguous short query, got {[r.name for r in results]}"


def test_catalog_exact_match_still_works():
    from custom_components.voice_jellyfin.jellyfin.catalog import JellyfinCatalog
    catalog = JellyfinCatalog()
    catalog.build([MediaItem(id="m1", name="Interstellar", type="Movie")])
    results = catalog.search("interstellar")
    assert len(results) == 1
    assert results[0].name == "Interstellar"


def test_catalog_clear_winner_short_query():
    from custom_components.voice_jellyfin.jellyfin.catalog import JellyfinCatalog
    catalog = JellyfinCatalog()
    catalog.build([
        MediaItem(id="m1", name="Us", type="Movie"),
        MediaItem(id="m2", name="The Dark Knight", type="Movie"),
    ])
    # "Us" is 2 chars but it's the ONLY match at high score
    results = catalog.search("us", limit=5)
    # Either returns Us (clear winner) or empty (ambiguous) — either is safe
    for r in results:
        assert r.name == "Us"


# ---------------------------------------------------------------------------
# JellyfinClient new methods
# ---------------------------------------------------------------------------

def _make_auth():
    return JellyfinAuth(url="http://localhost:8096", api_key="test-key")


def _mock_response(json_data, status=200):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.read = AsyncMock(return_value=b"")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_session(response):
    s = MagicMock()
    s.closed = False
    s.get = MagicMock(return_value=response)
    s.post = MagicMock(return_value=response)
    s.delete = MagicMock(return_value=response)
    s.close = AsyncMock()
    return s


@pytest.mark.asyncio
async def test_async_next_track_posts_to_next_endpoint():
    resp = _mock_response({})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(_make_auth())
        await client.async_next_track("sess-001")
    assert session.post.call_args[0][0].endswith("/Sessions/sess-001/Playing/Next")


@pytest.mark.asyncio
async def test_async_set_favorite_posts():
    resp = _mock_response({})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(_make_auth())
        await client.async_set_favorite("user-001", "item-001", is_favorite=True)
    assert session.post.called
    assert "FavoriteItems/item-001" in session.post.call_args[0][0]


@pytest.mark.asyncio
async def test_async_set_favorite_deletes_when_removing():
    resp = _mock_response({})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(_make_auth())
        await client.async_set_favorite("user-001", "item-001", is_favorite=False)
    assert session.delete.called
    assert "FavoriteItems/item-001" in session.delete.call_args[0][0]


@pytest.mark.asyncio
async def test_async_get_series_play_target_with_season():
    ep_payload = {"Items": [{"Id": "s3e1", "Name": "No Más", "UserData": {"PlaybackPositionTicks": 0}}]}
    resp = _mock_response(ep_payload)
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(_make_auth())
        result = await client.async_get_series_play_target("series-001", "user-001", season_number=3)
    assert result == ("s3e1", 0)
    # Verify Season=3 was passed
    call_params = session.get.call_args[1].get("params", {})
    assert call_params.get("Season") == 3


@pytest.mark.asyncio
async def test_async_set_bitrate_limit_writes_user_policy():
    # GET /Users/{id} returns the policy, POST /Users/{id}/Policy writes it back.
    resp = _mock_response({"Id": "user-001", "Policy": {"IsAdministrator": True, "RemoteClientBitrateLimit": 0}})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(_make_auth())
        ok = await client.async_set_bitrate_limit("user-001", 4000)

    assert ok is True
    url = session.post.call_args[0][0]
    assert url.endswith("/Users/user-001/Policy")
    body = session.post.call_args[1].get("json", {})
    # Stored in bits per second, and the rest of the policy survives the write.
    assert body["RemoteClientBitrateLimit"] == 4_000_000
    assert body["IsAdministrator"] is True


@pytest.mark.asyncio
async def test_async_set_bitrate_limit_reports_permission_failure():
    get_resp = _mock_response({"Id": "user-001", "Policy": {"RemoteClientBitrateLimit": 0}})
    post_resp = _mock_response({}, status=403)
    session = _mock_session(get_resp)
    session.post = MagicMock(return_value=post_resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(_make_auth())
        ok = await client.async_set_bitrate_limit("user-001", 4000)

    assert session.post.called
    assert ok is False


@pytest.mark.asyncio
async def test_async_get_bitrate_limit_returns_kbps():
    resp = _mock_response({"Id": "user-001", "Policy": {"RemoteClientBitrateLimit": 8_000_000}})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(_make_auth())
        assert await client.async_get_bitrate_limit("user-001") == 8000


@pytest.mark.asyncio
async def test_async_play_does_not_send_bitrate_param():
    # Jellyfin's PlayRequest has no bitrate field; the cap lives on the user policy.
    resp = _mock_response({})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(_make_auth())
        await client.async_play("sess-001", "item-001")
    params = session.post.call_args[1].get("params", {})
    assert "MaxStreamingBitrate" not in params


@pytest.mark.asyncio
async def test_async_skip_intro_seeks_to_next_chapter():
    # Session with item
    sessions_payload = [{
        "Id": "sess-001", "UserId": "user-001",
        "NowPlayingItem": {"Id": "item-001", "Name": "Bluey S01E01", "Type": "Episode"},
        "PlayState": {"PositionTicks": 10_000_000, "IsPaused": False},
    }]
    item_payload = {
        "Id": "item-001",
        "Chapters": [
            {"StartPositionTicks": 0, "Name": "Intro"},
            {"StartPositionTicks": 60_000_000, "Name": "Main"},
        ]
    }

    get_responses = [sessions_payload, item_payload]
    idx = [0]

    def _get_response(*a, **kw):
        r = _mock_response(get_responses[idx[0]])
        idx[0] = min(idx[0] + 1, len(get_responses) - 1)
        return r

    http_session = MagicMock()
    http_session.closed = False
    http_session.get = MagicMock(side_effect=_get_response)
    http_session.post = MagicMock(return_value=_mock_response({}))
    http_session.close = AsyncMock()

    with patch("aiohttp.ClientSession", return_value=http_session):
        client = JellyfinClient(_make_auth())
        result = await client.async_skip_intro("sess-001")

    assert result is True
    # Should have seeked to chapter 1 start (60s)
    seek_params = http_session.post.call_args[1].get("params", {})
    assert seek_params.get("seekPositionTicks") == 60_000_000


# ---------------------------------------------------------------------------
# Rule-based quality phrase matching (no AI provider)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phrase,intent,params",
    [
        ("lower the quality", "QUALITY_DOWN", {}),
        ("turn the quality down", "QUALITY_DOWN", {}),
        ("it keeps buffering", "QUALITY_DOWN", {}),
        ("raise the quality", "QUALITY_UP", {}),
        ("set the quality to low", "SET_QUALITY", {"level": "low"}),
        ("make it lowest quality", "SET_QUALITY", {"level": "lowest"}),
        ("set quality to medium", "SET_QUALITY", {"level": "medium"}),
        ("cap the bitrate at 3 mbps", "SET_QUALITY", {"bitrate_kbps": 3000}),
        ("set the bitrate to 1500 kbps", "SET_QUALITY", {"bitrate_kbps": 1500}),
        ("remove the quality limit", "SET_QUALITY", {"level": "auto"}),
        ("reset the quality", "SET_QUALITY", {"level": "auto"}),
        ("what is the bitrate", "QUALITY_STATUS", {}),
    ],
)
def test_quality_phrases_route_without_ai(phrase, intent, params):
    router = _make_router()
    result = router._rule_based_intent(phrase)
    assert result.intent == intent
    assert result.params == params


@pytest.mark.parametrize(
    "phrase,intent",
    [
        ("play breaking bad", "PLAY"),
        # A title containing a quality word must still be treated as media.
        ("play High Quality", "PLAY"),
        ("search for high quality documentaries", "SEARCH"),
        ("pause", "PAUSE"),
    ],
)
def test_quality_matching_does_not_swallow_media_commands(phrase, intent):
    router = _make_router()
    assert router._rule_based_intent(phrase).intent == intent


# ---------------------------------------------------------------------------
# Numbered quality scale (1-5 → 2/4/6/8/10 Mbps)
# ---------------------------------------------------------------------------

from custom_components.voice_jellyfin.const import (  # noqa: E402
    BITRATE_PRESETS_KBPS,
    QUALITY_SCALE_KBPS,
)


def test_quality_scale_steps_by_two_megabits():
    assert BITRATE_PRESETS_KBPS == [2000, 4000, 6000, 8000, 10000]
    assert QUALITY_SCALE_KBPS[1] == 2000
    assert QUALITY_SCALE_KBPS[3] == 6000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase,expected_kbps",
    [
        ("quality one", 2000),
        ("quality three", 6000),
        ("quality five", 10000),
        ("set the quality to 2", 4000),
        ("quality level 4", 8000),
    ],
)
async def test_numbered_quality_levels(phrase, expected_kbps):
    jellyfin = _quality_jellyfin(session=None, current_kbps=0)

    await _route(jellyfin, phrase, presets=BITRATE_PRESETS_KBPS)

    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", expected_kbps)


@pytest.mark.asyncio
async def test_numbered_level_is_spoken_back_with_its_bitrate():
    jellyfin = _quality_jellyfin(session=None, current_kbps=0)

    result = await _route(jellyfin, "quality three", presets=BITRATE_PRESETS_KBPS)

    assert "level 3" in result.speech_reply
    assert "6 megabits per second" in result.speech_reply


@pytest.mark.asyncio
async def test_stepping_up_walks_the_two_megabit_ladder():
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=2000)

    await _route(jellyfin, "higher quality", presets=BITRATE_PRESETS_KBPS)

    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 4000)


@pytest.mark.asyncio
async def test_stepping_down_walks_the_two_megabit_ladder():
    session = _playing_session()
    jellyfin = _quality_jellyfin(session, current_kbps=6000)

    await _route(jellyfin, "lower quality", presets=BITRATE_PRESETS_KBPS)

    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 4000)


@pytest.mark.asyncio
async def test_status_reports_the_level_number():
    jellyfin = _quality_jellyfin(session=None, current_kbps=8000)

    result = await _route(jellyfin, "what's the quality", presets=BITRATE_PRESETS_KBPS)

    assert "level 4" in result.speech_reply


@pytest.mark.asyncio
async def test_number_above_the_scale_is_read_as_megabits():
    jellyfin = _quality_jellyfin(session=None, current_kbps=0)

    await _route(jellyfin, "set the bitrate to 12", presets=BITRATE_PRESETS_KBPS)

    jellyfin.async_set_bitrate_limit.assert_awaited_once_with("user-001", 12000)


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("quality one", {"level": "1"}),
        ("quality 5", {"level": "5"}),
        ("set quality to three", {"level": "3"}),
        # Past the top of the scale, a bare number means megabits.
        ("set the bitrate to 12", {"bitrate_kbps": 12000}),
        # An explicit unit always wins over the level reading.
        ("set the quality to 3 mbps", {"bitrate_kbps": 3000}),
    ],
)
def test_numbered_phrases_route_without_ai(phrase, expected):
    router = _make_router()
    result = router._rule_based_intent(phrase)
    assert result.intent == "SET_QUALITY"
    assert result.params == expected
