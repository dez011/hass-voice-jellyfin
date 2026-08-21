"""Tests for the JellyfinClient."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.voice_jellyfin.jellyfin.auth import JellyfinAuth
from custom_components.voice_jellyfin.jellyfin.client import JellyfinClient
from custom_components.voice_jellyfin.jellyfin.models import (
    Library,
    MediaItem,
    PlaybackSession,
)


def _make_auth(url: str = "http://localhost:8096") -> JellyfinAuth:
    return JellyfinAuth(url=url, api_key="test-key")


def _mock_response(json_data, status: int = 200) -> MagicMock:
    """Build a minimal async context manager mock for aiohttp responses."""
    resp = MagicMock()
    resp.status = status
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value=json_data)
    resp.read = AsyncMock(return_value=b"")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_session(response: MagicMock) -> MagicMock:
    session = MagicMock()
    session.closed = False
    session.get = MagicMock(return_value=response)
    session.post = MagicMock(return_value=response)
    session.delete = MagicMock(return_value=response)
    session.close = AsyncMock()
    return session


@pytest.fixture
def auth():
    return _make_auth()


@pytest.mark.asyncio
async def test_async_connect_success(auth):
    resp = _mock_response({"Version": "10.9.0", "ProductName": "Jellyfin Server"})
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        data = await client.async_connect()
    assert data["Version"] == "10.9.0"


@pytest.mark.asyncio
async def test_async_connect_raises_on_invalid_api_key(auth):
    resp = _mock_response({}, status=401)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        with pytest.raises(PermissionError, match="API key is invalid"):
            await client.async_connect()


@pytest.mark.asyncio
async def test_async_get_libraries(auth):
    payload = [
        {"ItemId": "lib-001", "Name": "Movies", "CollectionType": "movies"},
        {"ItemId": "lib-002", "Name": "TV Shows", "CollectionType": "tvshows"},
    ]
    resp = _mock_response(payload)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        libs = await client.async_get_libraries()
    assert len(libs) == 2
    assert isinstance(libs[0], Library)
    assert libs[0].name == "Movies"
    assert libs[1].type == "tvshows"


@pytest.mark.asyncio
async def test_async_search_returns_media_items(auth):
    payload = {
        "Items": [
            {"Id": "item-001", "Name": "The Dark Knight", "Type": "Movie", "ProductionYear": 2008, "Genres": ["Action"]},
            {"Id": "item-002", "Name": "Batman Begins", "Type": "Movie", "ProductionYear": 2005, "Genres": ["Action"]},
        ],
        "TotalRecordCount": 2,
    }
    resp = _mock_response(payload)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        items = await client.async_search("batman")
    assert len(items) == 2
    assert isinstance(items[0], MediaItem)
    assert items[0].name == "The Dark Knight"
    assert items[0].year == 2008


@pytest.mark.asyncio
async def test_async_get_resume_items(auth):
    payload = {
        "Items": [
            {"Id": "item-ep1", "Name": "Breaking Bad S01E01", "Type": "Episode"},
        ],
        "TotalRecordCount": 1,
    }
    resp = _mock_response(payload)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        items = await client.async_get_resume_items("user-001")
    assert len(items) == 1
    assert items[0].type == "Episode"


@pytest.mark.asyncio
async def test_async_play_sends_post(auth):
    resp = _mock_response({})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        await client.async_play("sess-001", "item-001")
    session.post.assert_called_once()
    call_url = session.post.call_args[0][0]
    assert "Sessions/sess-001/Playing" in call_url


@pytest.mark.asyncio
async def test_async_stop_posts_to_stop_endpoint(auth):
    resp = _mock_response({})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        await client.async_stop("sess-001")
    session.post.assert_called_once()
    assert session.post.call_args[0][0].endswith("/Sessions/sess-001/Playing/Stop")


@pytest.mark.asyncio
async def test_async_pause_posts_to_pause_endpoint(auth):
    resp = _mock_response({})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        await client.async_pause("sess-001")
    session.post.assert_called_once()
    assert session.post.call_args[0][0].endswith("/Sessions/sess-001/Playing/Pause")


@pytest.mark.asyncio
async def test_async_unpause_posts_to_unpause_endpoint(auth):
    resp = _mock_response({})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        await client.async_unpause("sess-001")
    session.post.assert_called_once()
    assert session.post.call_args[0][0].endswith("/Sessions/sess-001/Playing/Unpause")


@pytest.mark.asyncio
async def test_async_search_falls_back_to_raw_query(auth):
    """Zero filtered hits should trigger one unfiltered retry with the raw query."""
    from custom_components.voice_jellyfin.jellyfin.catalog import JellyfinCatalog

    family_guy = MediaItem(id="item-fg", name="Family Guy", type="Series", genres=["Comedy"])
    catalog = JellyfinCatalog()
    catalog.build([family_guy])

    client = JellyfinClient(_make_auth())
    client._catalog = catalog

    # Parser output for "family guy": genre stripped, query mangled
    items = await client.async_search(
        "guy", limit=5, genre_hint="Family", raw_query="family guy"
    )
    assert [i.name for i in items] == ["Family Guy"]


@pytest.mark.asyncio
async def test_async_get_sessions(auth):
    payload = [
        {
            "Id": "sess-001",
            "UserId": "user-001",
            "NowPlayingItem": {"Id": "item-001", "Name": "Interstellar", "Type": "Movie"},
            "PlayState": {"PositionTicks": 50_000_000, "IsPaused": False},
        }
    ]
    resp = _mock_response(payload)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        sessions = await client.async_get_sessions()
    assert len(sessions) == 1
    sess = sessions[0]
    assert isinstance(sess, PlaybackSession)
    assert sess.item is not None
    assert sess.item.name == "Interstellar"
    assert sess.position_seconds == pytest.approx(5.0)
    assert not sess.is_paused


@pytest.mark.asyncio
async def test_async_close(auth):
    session = MagicMock()
    session.closed = False
    session.close = AsyncMock()
    session.get = MagicMock(return_value=_mock_response({"Version": "10.9"}))
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        await client.async_connect()
        await client.async_close()
    session.close.assert_called_once()


# ---------------------------------------------------------------------------
# Regression tests: status handling, user resolution, catalog interplay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_error_status_raises_clean_error(auth):
    """A 502 from a reverse proxy must raise ConnectionError, not crash in
    resp.json() on the HTML error body."""
    resp = _mock_response(None, status=502)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        with pytest.raises(ConnectionError, match="502"):
            await client.async_get_sessions()


@pytest.mark.asyncio
async def test_revoked_key_raises_permission_error(auth):
    resp = _mock_response(None, status=401)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        with pytest.raises(PermissionError):
            await client.async_get_libraries()


@pytest.mark.asyncio
async def test_effective_user_id_resolved_from_users_endpoint(auth):
    """With an API key and no configured user, the client resolves and
    caches a user id from /Users instead of building /Users//... URLs."""
    resp = _mock_response([{"Id": "resolved-user", "Name": "Miguel"}])
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        uid = await client._async_effective_user_id()
    assert uid == "resolved-user"
    assert auth.user_id == "resolved-user"
    # Cached — second call must not hit the API again
    session.get.reset_mock()
    uid2 = await client._async_effective_user_id()
    assert uid2 == "resolved-user"
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_effective_user_id_prefers_explicit_argument(auth):
    client = JellyfinClient(auth)
    assert await client._async_effective_user_id("explicit") == "explicit"


@pytest.mark.asyncio
async def test_resume_items_without_any_user_returns_empty(auth):
    """Unresolvable user → empty list, never a /Users//Items/Resume 404."""
    resp = _mock_response([], status=200)
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        items = await client.async_get_resume_items("")
    assert items == []
    for c in session.get.call_args_list:
        assert "/Users//" not in c[0][0]


@pytest.mark.asyncio
async def test_recently_added_includes_user_id(auth):
    auth.user_id = "user-42"
    resp = _mock_response([])
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        await client.async_get_recently_added()
    params = session.get.call_args[1]["params"]
    assert params["UserId"] == "user-42"


@pytest.mark.asyncio
async def test_catalog_bypassed_for_episode_search(auth):
    """The catalog only indexes Movies/Series — an Episode search must go
    to the API even when the catalog is built."""
    from custom_components.voice_jellyfin.jellyfin.catalog import JellyfinCatalog

    catalog = JellyfinCatalog()
    catalog.build([MediaItem(id="m1", name="Some Movie", type="Movie")])

    payload = {"Items": [{"Id": "ep1", "Name": "Pilot", "Type": "Episode"}]}
    resp = _mock_response(payload)
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        client._catalog = catalog
        items = await client.async_search("pilot", type_filter="Episode")
    assert [i.name for i in items] == ["Pilot"]
    session.get.assert_called()


@pytest.mark.asyncio
async def test_catalog_miss_falls_back_to_api(auth):
    from custom_components.voice_jellyfin.jellyfin.catalog import JellyfinCatalog

    catalog = JellyfinCatalog()
    catalog.build([MediaItem(id="m1", name="Unrelated", type="Movie")])

    payload = {"Items": [{"Id": "a1", "Name": "Yellow Submarine", "Type": "Audio"}]}
    resp = _mock_response(payload)
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        client._catalog = catalog
        items = await client.async_search("yellow submarine")
    assert [i.name for i in items] == ["Yellow Submarine"]


@pytest.mark.asyncio
async def test_build_catalog_paginates_by_items_received(auth):
    """Pagination must advance by len(page) and keep going when the server
    returns short pages."""
    pages = [
        {"Items": [{"Id": f"i{n}", "Name": f"Movie {n}", "Type": "Movie"} for n in range(3)],
         "TotalRecordCount": 5},
        {"Items": [{"Id": "i3", "Name": "Movie 3", "Type": "Movie"},
                   {"Id": "i4", "Name": "Movie 4", "Type": "Movie"}],
         "TotalRecordCount": 5},
    ]
    responses = [_mock_response(p) for p in pages]
    session = _mock_session(responses[0])
    session.get = MagicMock(side_effect=responses)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        await client.async_build_catalog()
    assert client._catalog.size == 5
    # Second request must start where the first page actually ended
    second_params = session.get.call_args_list[1][1]["params"]
    assert second_params["StartIndex"] == 3


@pytest.mark.asyncio
async def test_skip_intro_handles_null_chapter_names(auth):
    """Jellyfin chapter names can be JSON null — must not crash and must
    fall back to the +90s seek."""
    sessions_payload = [
        {
            "Id": "sess-1",
            "UserId": "u1",
            "NowPlayingItem": {"Id": "item-1", "Name": "Show", "Type": "Episode"},
            "PlayState": {"PositionTicks": 0, "IsPaused": False},
        }
    ]
    item_payload = {"Chapters": [{"Name": None, "StartPositionTicks": 0}]}

    responses = [_mock_response(sessions_payload), _mock_response(item_payload)]
    post_resp = _mock_response({})
    session = _mock_session(post_resp)
    session.get = MagicMock(side_effect=responses)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        result = await client.async_skip_intro("sess-1")
    assert result is True
    seek_params = session.post.call_args[1]["params"]
    assert seek_params["seekPositionTicks"] == 90 * 10_000_000


@pytest.mark.asyncio
async def test_series_play_target_without_user_still_finds_first_episode(auth):
    """With no resolvable user the resume/next-up steps are skipped, but
    S1E1 lookup must still work (and never produce /Users//... URLs)."""
    responses = [
        _mock_response([]),  # /Users → no users resolvable
        _mock_response({"Items": [{"Id": "ep-1", "Name": "S1E1"}]}),  # episodes
    ]
    session = _mock_session(responses[0])
    session.get = MagicMock(side_effect=responses)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        target = await client.async_get_series_play_target("series-1", "")
    assert target == ("ep-1", 0)
    for c in session.get.call_args_list:
        assert "/Users//" not in c[0][0]


# ---------------------------------------------------------------------------
# Multi-device/user targeting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_get_users(auth):
    payload = [
        {"Id": "u1", "Name": "Miguel"},
        {"Id": "u2", "Name": "Brother"},
    ]
    resp = _mock_response(payload)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        users = await client.async_get_users()
    assert users == [{"id": "u1", "name": "Miguel"}, {"id": "u2", "name": "Brother"}]


@pytest.mark.asyncio
async def test_async_get_users_skips_entries_without_id(auth):
    payload = [{"Name": "No ID"}, {"Id": "u1", "Name": "Has ID"}]
    resp = _mock_response(payload)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        users = await client.async_get_users()
    assert users == [{"id": "u1", "name": "Has ID"}]


@pytest.mark.asyncio
async def test_async_resume_prefers_device_filter_within_user_pool(auth):
    """Two sessions both belong to the requesting user; device_filter picks
    the one on the targeted TV instead of whichever comes first."""
    resume_payload = {"Items": [{"Id": "ep1", "Name": "Show", "UserData": {"PlaybackPositionTicks": 500}}]}
    sessions_payload = [
        {"Id": "sess-living-room", "UserId": "u1", "DeviceName": "Living Room", "PlayState": {}},
        {"Id": "sess-bedroom", "UserId": "u1", "DeviceName": "Bedroom", "PlayState": {}},
    ]
    responses = [_mock_response(resume_payload), _mock_response(sessions_payload)]
    post_resp = _mock_response({})
    session = _mock_session(post_resp)
    session.get = MagicMock(side_effect=responses)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        await client.async_resume("u1", device_filter="bedroom")
    play_call = session.post.call_args
    assert "sess-bedroom" in play_call[0][0]


@pytest.mark.asyncio
async def test_async_resume_falls_back_to_first_in_pool_without_filter(auth):
    resume_payload = {"Items": [{"Id": "ep1", "Name": "Show"}]}
    sessions_payload = [{"Id": "sess-first", "UserId": "u1", "PlayState": {}}]
    responses = [_mock_response(resume_payload), _mock_response(sessions_payload)]
    post_resp = _mock_response({})
    session = _mock_session(post_resp)
    session.get = MagicMock(side_effect=responses)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        title = await client.async_resume("u1")
    assert title == "Show"


@pytest.mark.asyncio
async def test_async_get_now_playing_respects_device_filter(auth):
    payload = [
        {"Id": "s1", "DeviceName": "Other TV", "NowPlayingItem": {"Id": "i1", "Name": "Other Show"}, "PlayState": {"IsPaused": False}},
        {"Id": "s2", "DeviceName": "My TV", "NowPlayingItem": {"Id": "i2", "Name": "My Show"}, "PlayState": {"IsPaused": False}},
    ]
    resp = _mock_response(payload)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        result = await client.async_get_now_playing(device_filter="My TV")
    assert result == ("My Show", "My Show")


@pytest.mark.asyncio
async def test_sessions_carry_client_and_device_info(auth):
    payload = [
        {
            "Id": "s1", "UserId": "u1", "UserName": "Miguel",
            "Client": "Astra", "DeviceName": "Bedroom Fire TV", "DeviceId": "dev-1",
            "NowPlayingItem": {"Id": "i1", "Name": "Show"},
            "PlayState": {"IsPaused": False},
        }
    ]
    resp = _mock_response(payload)
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        sessions = await client.async_get_sessions()
    sess = sessions[0]
    assert sess.client == "Astra"
    assert sess.device_name == "Bedroom Fire TV"
    assert sess.device_id == "dev-1"
    assert sess.user_name == "Miguel"
