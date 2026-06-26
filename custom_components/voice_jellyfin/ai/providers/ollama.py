"""Ollama local LLM provider with streaming support."""
from __future__ import annotations

import json
import logging
from typing import Optional

import aiohttp

from ..base import AIProvider

_LOGGER = logging.getLogger(__name__)


class OllamaProvider(AIProvider):
    """Communicates with a local Ollama server via aiohttp.

    Streaming mode reads the NDJSON response line-by-line for lower latency.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 11434,
        https: bool = False,
        model: str = "llama3",
        context_size: int = 4096,
        keep_alive: str = "5m",
        streaming: bool = True,
        timeout: int = 60,
    ) -> None:
        self._host = host
        self._port = port
        self._https = https
        self._model = model
        self._context_size = context_size
        self._keep_alive = keep_alive
        self._streaming = streaming
        self._timeout = timeout

    @property
    def name(self) -> str:
        return f"Ollama ({self._model})"

    def _base_url(self) -> str:
        scheme = "https" if self._https else "http"
        return f"{scheme}://{self._host}:{self._port}"

    async def async_query(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        """POST /api/chat and return the model's response."""
        url = f"{self._base_url()}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            "stream": self._streaming,
            "options": {
                "num_ctx": self._context_size,
            },
            "keep_alive": self._keep_alive,
        }

        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                resp.raise_for_status()
                if self._streaming:
                    return await self._read_stream(resp)
                else:
                    data = await resp.json()
                    return (data.get("message", {}).get("content") or "").strip()

    async def _read_stream(
        self, resp: aiohttp.ClientResponse
    ) -> str:
        """Read the NDJSON streaming response and concatenate content tokens."""
        parts: list[str] = []
        async for raw_line in resp.content:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            token = chunk.get("message", {}).get("content", "")
            if token:
                parts.append(token)
            if chunk.get("done"):
                break
        return "".join(parts).strip()

    # ------------------------------------------------------------------
    # Static helper for config flow model discovery
    # ------------------------------------------------------------------

    @staticmethod
    async def async_list_models(
        host: str,
        port: int,
        https: bool = False,
    ) -> list[str]:
        """Return the list of models available on an Ollama server.

        Calls GET /api/tags and returns model name strings.
        Raises on connection failure.
        """
        scheme = "https" if https else "http"
        url = f"{scheme}://{host}:{port}/api/tags"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.json()
        models = data.get("models", [])
        return [m["name"] for m in models if "name" in m]
