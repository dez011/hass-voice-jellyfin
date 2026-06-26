"""Jellyfin WebSocket client for real-time session events."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

_KEEPALIVE_INTERVAL = 30  # seconds


class JellyfinWebSocket:
    """Connects to the Jellyfin WebSocket endpoint and dispatches messages.

    Supported inbound message types:
      - SessionsStart / SessionsStop
      - PlaybackStart / PlaybackProgress / PlaybackStopped
      - KeepAlive (echo back)
    """

    def __init__(self) -> None:
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._running = False

    async def async_connect(
        self,
        url: str,
        api_key: str,
        on_message_callback: Callable[[str, Any], None],
    ) -> None:
        """Open the WebSocket connection and start listen + keepalive tasks.

        :param url: Jellyfin base HTTP URL (http://host:8096).  Will be
                    converted to ws:// automatically.
        :param api_key: Jellyfin API key used for authentication.
        :param on_message_callback: Called with (message_type, data) for
                                    every inbound message.
        """
        ws_url = (
            url.rstrip("/")
            .replace("https://", "wss://")
            .replace("http://", "ws://")
        )
        ws_url = f"{ws_url}/socket?api_key={api_key}&deviceId=voice_jellyfin_ha"

        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(ws_url)
        self._running = True
        _LOGGER.debug("Jellyfin WebSocket connected: %s", ws_url)

        self._listen_task = asyncio.ensure_future(
            self._listen(on_message_callback)
        )
        self._keepalive_task = asyncio.ensure_future(self._keepalive())

    async def async_disconnect(self) -> None:
        """Gracefully close the WebSocket connection."""
        self._running = False
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self._listen_task:
            self._listen_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        _LOGGER.debug("Jellyfin WebSocket disconnected")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _listen(
        self, callback: Callable[[str, Any], None]
    ) -> None:
        """Receive messages in a loop until the connection closes."""
        assert self._ws is not None
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._handle_text(msg.data, callback)
            elif msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                _LOGGER.warning("WebSocket closed/errored: %s", msg)
                break
        self._running = False

    async def _handle_text(
        self, raw: str, callback: Callable[[str, Any], None]
    ) -> None:
        """Parse a JSON message and invoke the callback."""
        try:
            payload: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            _LOGGER.debug("Non-JSON WS message: %s", raw[:120])
            return

        msg_type: str = payload.get("MessageType", "")
        data: Any = payload.get("Data")

        if msg_type == "KeepAlive":
            await self._send({"MessageType": "KeepAlive"})
            return

        if msg_type in (
            "SessionsStart",
            "SessionsStop",
            "PlaybackStart",
            "PlaybackProgress",
            "PlaybackStopped",
        ):
            try:
                callback(msg_type, data)
            except Exception:  # pragma: no cover
                _LOGGER.exception("Error in WS message callback")

    async def _keepalive(self) -> None:
        """Send a KeepAlive message every 30 seconds."""
        while self._running:
            await asyncio.sleep(_KEEPALIVE_INTERVAL)
            if self._ws and not self._ws.closed:
                await self._send({"MessageType": "KeepAlive"})

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_str(json.dumps(payload))
            except Exception as exc:  # pragma: no cover
                _LOGGER.debug("WS send error: %s", exc)
