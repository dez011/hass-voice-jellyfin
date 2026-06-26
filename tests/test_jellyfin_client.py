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
async def test_async_connect_raises_on_http_error(auth):
    resp = _mock_response({}, status=401)
    resp.raise_for_status = MagicMock(side_effect=Exception("401 Unauthorized"))
    with patch("aiohttp.ClientSession", return_value=_mock_session(resp)):
        client = JellyfinClient(auth)
        with pytest.raises(Exception, match="401"):
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
async def test_async_stop_sends_delete(auth):
    resp = _mock_response({})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        client = JellyfinClient(auth)
        await client.async_stop("sess-001")
    session.delete.assert_called_once()


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
