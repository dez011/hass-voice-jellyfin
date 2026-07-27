"""Tests for the Jellyfin WebSocket client."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.voice_jellyfin.jellyfin.websocket import JellyfinWebSocket


def _make_ws():
    ws = MagicMock()
    ws.closed = False
    ws.send_str = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _make_session(ws=None, connect_error: Exception | None = None):
    session = MagicMock()
    session.closed = False
    session.close = AsyncMock()
    if connect_error is not None:
        session.ws_connect = AsyncMock(side_effect=connect_error)
    else:
        session.ws_connect = AsyncMock(return_value=ws)
    return session


@pytest.mark.asyncio
async def test_connect_sends_sessions_start_subscription():
    """Without a SessionsStart subscription the server pushes no events."""
    ws = _make_ws()

    async def _no_messages():
        return
        yield  # pragma: no cover

    ws.__aiter__ = lambda self: _no_messages()
    session = _make_session(ws=ws)

    client = JellyfinWebSocket()
    with patch("aiohttp.ClientSession", return_value=session):
        await client.async_connect("http://localhost:8096", "key", lambda t, d: None)
    await client.async_disconnect()

    sent = [json.loads(c.args[0]) for c in ws.send_str.call_args_list]
    assert any(m.get("MessageType") == "SessionsStart" for m in sent)


@pytest.mark.asyncio
async def test_failed_connect_closes_session():
    """A failed handshake must not leak the ClientSession."""
    session = _make_session(connect_error=OSError("connection refused"))
    client = JellyfinWebSocket()
    with patch("aiohttp.ClientSession", return_value=session):
        with pytest.raises(OSError):
            await client.async_connect("http://localhost:8096", "key", lambda t, d: None)
    session.close.assert_awaited_once()
    assert client._session is None


@pytest.mark.asyncio
async def test_sessions_message_dispatched_to_callback():
    client = JellyfinWebSocket()
    client._ws = _make_ws()
    received = []
    await client._handle_text(
        json.dumps({"MessageType": "Sessions", "Data": [{"Id": "s1"}]}),
        lambda t, d: received.append((t, d)),
    )
    assert received == [("Sessions", [{"Id": "s1"}])]


@pytest.mark.asyncio
async def test_keepalive_and_force_keepalive_are_echoed():
    client = JellyfinWebSocket()
    ws = _make_ws()
    client._ws = ws
    for msg_type in ("KeepAlive", "ForceKeepAlive"):
        await client._handle_text(json.dumps({"MessageType": msg_type}), lambda t, d: None)
    assert ws.send_str.await_count == 2
    for c in ws.send_str.call_args_list:
        assert json.loads(c.args[0]) == {"MessageType": "KeepAlive"}


@pytest.mark.asyncio
async def test_non_json_message_ignored():
    client = JellyfinWebSocket()
    received = []
    await client._handle_text("not json at all", lambda t, d: received.append(t))
    assert received == []


@pytest.mark.asyncio
async def test_callback_exception_does_not_propagate():
    client = JellyfinWebSocket()

    def _boom(t, d):
        raise RuntimeError("callback error")

    await client._handle_text(
        json.dumps({"MessageType": "PlaybackStart", "Data": {}}), _boom
    )  # must not raise


@pytest.mark.asyncio
async def test_disconnect_awaits_cancelled_tasks():
    client = JellyfinWebSocket()
    client._running = True

    async def _forever():
        await asyncio.sleep(3600)

    client._listen_task = asyncio.ensure_future(_forever())
    client._keepalive_task = asyncio.ensure_future(_forever())
    await client.async_disconnect()
    assert client._listen_task is None
    assert client._keepalive_task is None
