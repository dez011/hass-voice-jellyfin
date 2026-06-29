"""Intent router — maps AI JSON output to Jellyfin / TV actions."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .base import AIProvider
from .context import AIContext

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
You are an AI assistant that controls a Jellyfin media server{tv_clause}.
The user speaks voice commands and you must parse their intent.

You MUST respond with ONLY a valid JSON object — no prose, no markdown fences.
The JSON schema is:
{{
  "intent": "<one of the intents listed below>",
  "params": {{ <intent-specific key/value pairs> }},
  "speech": "<optional short spoken reply to the user>"
}}

Valid intents and their params:
- PLAY        params: query (string), library_id (optional string)
- SEARCH      params: query (string)
- NAVIGATE    params: direction ("up"|"down"|"left"|"right"|"select"|"back"|"home"|"page_up"|"page_down")
- FILTER      params: genre (optional string), year (optional int), library_id (optional string)
- RESUME      params: user_id (optional string)
- PAUSE       params: session_id (optional string)
- STOP        params: session_id (optional string)
- GO_HOME     params: {{}}
- GO_BACK     params: {{}}
- NAV_MODE_ON  params: {{}}
- NAV_MODE_OFF params: {{}}
- REPEAT      params: {{}}
- REVERSE     params: {{}}
- SELECT      params: {{}}
- SCROLL      params: direction ("up"|"down"), amount (optional int, default 1)

If you cannot determine the intent, default to SEARCH with the user's words as query.
Keep the "speech" field brief and natural — maximum 20 words.
"""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    """Result returned by IntentRouter.async_route."""

    intent: str
    params: dict[str, Any] = field(default_factory=dict)
    speech_reply: str = ""
    media_title: str = ""


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_TV_LABELS = {
    "apple_tv": "an Apple TV",
    "android_tv": "an Android TV",
}


class IntentRouter:
    """Parses a natural language command via AI and dispatches the action."""

    def __init__(
        self,
        jellyfin: Any,
        tv: Any,
        nav: Any,
        hass: Any,
        tv_type: str = "",
    ) -> None:
        self._jellyfin = jellyfin
        self._tv = tv
        self._nav = nav
        self._hass = hass
        tv_label = _TV_LABELS.get(tv_type)
        tv_clause = f" and {tv_label}" if tv_label else ""
        self._system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(tv_clause=tv_clause)

    async def async_route(
        self,
        text: str,
        provider: Optional[AIProvider],
        context: AIContext,
    ) -> IntentResult:
        """Route *text* through the AI and dispatch the resolved intent.

        :param text: Raw voice command text.
        :param provider: Active AIProvider implementation.
        :param context: Shared AIContext for this session.
        :returns: IntentResult with intent, params, reply and media title.
        """
        context.add_turn("user", text)

        if provider is None:
            _LOGGER.warning("No AI provider configured; defaulting to SEARCH")
            return await self._dispatch(
                IntentResult(intent="SEARCH", params={"query": text}), context
            )

        try:
            raw = await provider.async_query(
                messages=context.get_messages(),
                system_prompt=self._system_prompt,
            )
            result = self._parse(raw)
        except Exception as exc:
            _LOGGER.error("AI query failed: %s", exc)
            result = IntentResult(
                intent="SEARCH",
                params={"query": text},
                speech_reply="Sorry, I had trouble understanding that.",
            )

        result = await self._dispatch(result, context)
        context.add_turn("assistant", result.speech_reply or "Done.")
        context.last_action = result.intent
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse(self, raw: str) -> IntentResult:
        """Parse raw JSON from the AI into an IntentResult."""
        raw = raw.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            _LOGGER.warning("AI returned non-JSON: %s", raw[:200])
            return IntentResult(intent="SEARCH", params={"query": raw})

        return IntentResult(
            intent=data.get("intent", "SEARCH").upper(),
            params=data.get("params", {}),
            speech_reply=data.get("speech", ""),
        )

    async def _dispatch(
        self, result: IntentResult, context: AIContext
    ) -> IntentResult:
        """Execute the action described by *result*."""
        intent = result.intent
        params = result.params

        try:
            if intent == "PLAY":
                result = await self._handle_play(result, context)
            elif intent == "SEARCH":
                result = await self._handle_search(result, context)
            elif intent == "NAVIGATE":
                await self._handle_navigate(params)
            elif intent == "FILTER":
                self._handle_filter(params, context)
            elif intent == "RESUME":
                result = await self._handle_resume(result, params)
            elif intent == "PAUSE":
                await self._handle_pause(params)
            elif intent == "STOP":
                await self._handle_stop(params)
            elif intent in ("GO_HOME", "HOME"):
                await self._send_key("home")
            elif intent == "GO_BACK":
                await self._send_key("back")
            elif intent == "NAV_MODE_ON":
                if self._nav:
                    await self._nav.async_activate()
            elif intent == "NAV_MODE_OFF":
                if self._nav:
                    await self._nav.async_deactivate()
            elif intent in ("REPEAT",):
                if context.last_action:
                    result.speech_reply = f"Repeating {context.last_action}."
            elif intent == "REVERSE":
                await self._send_key("back")
            elif intent == "SELECT":
                await self._send_key("select")
            elif intent == "SCROLL":
                direction = params.get("direction", "down")
                amount = int(params.get("amount", 1))
                for _ in range(amount):
                    await self._send_key(direction)
        except Exception as exc:
            _LOGGER.error("Intent dispatch error for %s: %s", intent, exc)
            result.speech_reply = result.speech_reply or "Sorry, that didn't work."

        return result

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_play(
        self, result: IntentResult, context: AIContext
    ) -> IntentResult:
        query = result.params.get("query", "")
        if not query:
            result.speech_reply = "What would you like to play?"
            return result

        if self._jellyfin:
            items = await self._jellyfin.async_search(query, limit=5)
            if items:
                item = items[0]
                sessions = await self._jellyfin.async_get_sessions()
                session = next(iter(sessions), None)
                if session:
                    await self._jellyfin.async_play(session.id, item.id)
                    result.media_title = item.name
                    result.speech_reply = (
                        result.speech_reply or f"Playing {item.name}."
                    )
                else:
                    result.speech_reply = "No active player session found."
            else:
                result.speech_reply = f"I couldn't find anything matching '{query}'."
        return result

    async def _handle_search(
        self, result: IntentResult, context: AIContext
    ) -> IntentResult:
        query = result.params.get("query", "")
        if self._jellyfin and query:
            items = await self._jellyfin.async_search(query, limit=10)
            if items:
                titles = ", ".join(i.name for i in items[:5])
                result.speech_reply = (
                    result.speech_reply or f"Found: {titles}."
                )
            else:
                result.speech_reply = f"Nothing found for '{query}'."
        return result

    async def _handle_navigate(self, params: dict[str, Any]) -> None:
        direction = params.get("direction", "")
        if direction:
            await self._send_key(direction)

    def _handle_filter(
        self, params: dict[str, Any], context: AIContext
    ) -> None:
        context.current_filter.update(
            {k: v for k, v in params.items() if v is not None}
        )
        if "library_id" in params:
            context.current_library = params["library_id"]

    async def _handle_resume(
        self, result: IntentResult, params: dict[str, Any]
    ) -> IntentResult:
        if self._jellyfin:
            user_id = params.get("user_id", self._jellyfin._auth.user_id or "")
            title = await self._jellyfin.async_resume(user_id)
            if title:
                result.media_title = title
                result.speech_reply = (
                    result.speech_reply or f"Resuming {title}."
                )
            else:
                result.speech_reply = "Nothing to resume."
        return result

    async def _handle_pause(self, params: dict[str, Any]) -> None:
        if self._jellyfin:
            session_id = params.get("session_id") or await self._active_session_id()
            if session_id:
                await self._jellyfin.async_pause(session_id)

    async def _handle_stop(self, params: dict[str, Any]) -> None:
        if self._jellyfin:
            session_id = params.get("session_id") or await self._active_session_id()
            if session_id:
                await self._jellyfin.async_stop(session_id)

    async def _active_session_id(self) -> Optional[str]:
        if not self._jellyfin:
            return None
        sessions = await self._jellyfin.async_get_sessions()
        active = next((s for s in sessions if s.item), None)
        return active.id if active else (sessions[0].id if sessions else None)

    async def _send_key(self, key: str) -> None:
        if self._tv:
            await self._tv.async_send_key(key)
        else:
            _LOGGER.debug("No TV controller configured; key %s ignored", key)
