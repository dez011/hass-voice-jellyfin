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
- PLAY         params: query (string), season (optional int), library_id (optional string)
- PLAY_LATEST  params: query (string) — play newest episode of a series
- SEARCH       params: query (string)
- NAVIGATE     params: direction ("up"|"down"|"left"|"right"|"select"|"back"|"home"|"page_up"|"page_down")
- FILTER       params: genre (optional string), year (optional int), library_id (optional string)
- RESUME       params: user_id (optional string)
- PAUSE        params: session_id (optional string)
- STOP         params: session_id (optional string)
- NEXT_EPISODE params: {{}} — skip to next episode
- SKIP_INTRO   params: {{}} — skip the intro of the current episode
- QUALITY_UP   params: {{}} — increase stream quality one step
- QUALITY_DOWN params: {{}} — lower stream quality one step
- FAVORITE     params: {{}} — add currently playing item to favorites
- UNFAVORITE   params: {{}} — remove currently playing item from favorites
- NOW_PLAYING  params: {{}} — ask what is currently playing
- OPEN_APP     params: {{}} — open the configured Jellyfin client app on the TV
- HOT_MIC_ON   params: {{}} — activate continuous listening / hot mic mode
- HOT_MIC_OFF  params: {{}} — deactivate continuous listening / hot mic mode
- GO_HOME      params: {{}}
- GO_BACK      params: {{}}
- NAV_MODE_ON  params: {{}}
- NAV_MODE_OFF params: {{}}
- REPEAT       params: {{}}
- REVERSE      params: {{}}
- SELECT       params: {{}}
- SCROLL       params: direction ("up"|"down"), amount (optional int, default 1)

Examples:
- "play season 3 of Breaking Bad" → PLAY, query="Breaking Bad", season=3
- "play the latest episode of Bluey" → PLAY_LATEST, query="Bluey"
- "open Jellyfin" → OPEN_APP
- "skip the intro" → SKIP_INTRO
- "lower the quality" or "it's buffering" → QUALITY_DOWN
- "next episode" → NEXT_EPISODE
- "add this to my favorites" → FAVORITE
- "what's playing?" → NOW_PLAYING

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
        preferred_client_package: str = "org.jellyfin.androidtv",
        bitrate_presets: Optional[list[int]] = None,
        current_bitrate_idx: int = -1,
    ) -> None:
        self._jellyfin = jellyfin
        self._tv = tv
        self._nav = nav
        self._hass = hass
        self._preferred_client_package = preferred_client_package
        from ..const import BITRATE_PRESETS_KBPS
        self._bitrate_presets = bitrate_presets or BITRATE_PRESETS_KBPS
        self._bitrate_idx = current_bitrate_idx  # -1 = auto (no cap)
        tv_label = _TV_LABELS.get(tv_type)
        tv_clause = f" and {tv_label}" if tv_label else ""
        self._system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(tv_clause=tv_clause)

    async def async_route(
        self,
        text: str,
        provider: Optional[AIProvider],
        context: AIContext,
        ai_enabled: bool = True,
    ) -> IntentResult:
        """Route *text* through the AI and dispatch the resolved intent.

        :param text: Raw voice command text.
        :param provider: Active AIProvider implementation.
        :param context: Shared AIContext for this session.
        :param ai_enabled: When False, skip AI and fall back to SEARCH.
        :returns: IntentResult with intent, params, reply and media title.
        """
        context.add_turn("user", text)

        if not ai_enabled or provider is None:
            result = self._rule_based_intent(text)
            _LOGGER.debug(
                "AI %s; rule-based intent=%s params=%s (raw=%r)",
                "disabled" if not ai_enabled else "provider missing",
                result.intent, result.params, text,
            )
            result = await self._dispatch(result, context)
            context.add_turn("assistant", result.speech_reply or "Done.")
            context.last_action = result.intent
            return result

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
            elif intent == "PLAY_LATEST":
                result = await self._handle_play_latest(result)
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
            elif intent == "NEXT_EPISODE":
                result = await self._handle_next_episode(result)
            elif intent == "SKIP_INTRO":
                result = await self._handle_skip_intro(result)
            elif intent == "QUALITY_UP":
                result = await self._handle_quality(result, direction=1)
            elif intent == "QUALITY_DOWN":
                result = await self._handle_quality(result, direction=-1)
            elif intent == "FAVORITE":
                result = await self._handle_favorite(result, add=True)
            elif intent == "UNFAVORITE":
                result = await self._handle_favorite(result, add=False)
            elif intent == "NOW_PLAYING":
                result = await self._handle_now_playing(result)
            elif intent == "OPEN_APP":
                result = await self._handle_open_app(result)
            elif intent == "HOT_MIC_ON":
                if self._nav:
                    await self._nav.async_activate_hot_mic()
                result.speech_reply = result.speech_reply or "Hot mic on. Listening for commands."
            elif intent == "HOT_MIC_OFF":
                if self._nav:
                    await self._nav.async_deactivate_hot_mic()
                result.speech_reply = result.speech_reply or "Hot mic off."
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
                try:
                    amount = int(params.get("amount", 1))
                except (ValueError, TypeError):
                    amount = 1
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
        raw_query = result.params.get("query", "")
        if not raw_query:
            result.speech_reply = "What would you like to play?"
            return result

        if not self._jellyfin:
            return result

        from ..jellyfin.query_parser import parse_query
        pq = parse_query(raw_query)
        season_number: Optional[int] = result.params.get("season")
        _LOGGER.debug("Play parsed: raw=%r query=%r type=%s year=%s genre=%s season=%s",
                      pq.raw, pq.query, pq.type_filter, pq.year, pq.genre_hint, season_number)

        items = await self._jellyfin.async_search(
            pq.query, limit=5,
            type_filter=pq.type_filter,
            genre_hint=pq.genre_hint,
            year=pq.year,
            raw_query=pq.raw,
        )
        if not items:
            result.speech_reply = f"I couldn't find anything matching '{raw_query}'."
            return result

        item = items[0]
        sessions = await self._jellyfin.async_get_sessions()
        session = next(iter(sessions), None)
        if not session:
            result.speech_reply = "No active player session found."
            return result

        play_id = item.id
        start_ticks = 0

        if item.type == "Series":
            user_id = self._jellyfin._auth.user_id or ""
            target = await self._jellyfin.async_get_series_play_target(
                item.id, user_id, season_number=season_number
            )
            if target:
                play_id, start_ticks = target

        await self._ensure_tv_awake()
        await self._jellyfin.async_play(session.id, play_id, start_ticks=start_ticks)
        result.media_title = item.name
        if season_number:
            result.speech_reply = result.speech_reply or f"Playing {item.name} season {season_number}."
        else:
            result.speech_reply = result.speech_reply or f"Playing {item.name}."
        return result

    async def _handle_search(
        self, result: IntentResult, context: AIContext
    ) -> IntentResult:
        raw_query = result.params.get("query", "")
        if self._jellyfin and raw_query:
            from ..jellyfin.query_parser import parse_query
            pq = parse_query(raw_query)
            items = await self._jellyfin.async_search(
                pq.query, limit=10,
                type_filter=pq.type_filter,
                genre_hint=pq.genre_hint,
                year=pq.year,
                raw_query=pq.raw,
            )
            query = pq.query  # use cleaned query in replies
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
        if not self._jellyfin:
            return result
        # Check for a currently paused session first — unpause it
        sessions = await self._jellyfin.async_get_sessions()
        paused = next((s for s in sessions if s.item and s.is_paused), None)
        if paused:
            await self._jellyfin.async_unpause(paused.id)
            name = paused.item.name if paused.item else "playback"
            result.media_title = name
            result.speech_reply = result.speech_reply or f"Resuming {name}."
            return result
        # No paused session — resume first in-progress item
        user_id = params.get("user_id", self._jellyfin._auth.user_id or "")
        title = await self._jellyfin.async_resume(user_id)
        if title:
            result.media_title = title
            result.speech_reply = result.speech_reply or f"Resuming {title}."
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

    async def _handle_play_latest(self, result: IntentResult) -> IntentResult:
        if not self._jellyfin:
            return result
        query = result.params.get("query", "")
        if not query:
            result.speech_reply = "Which show's latest episode?"
            return result
        items = await self._jellyfin.async_search(query, limit=5, type_filter="Series")
        if not items:
            result.speech_reply = f"I couldn't find a show called '{query}'."
            return result
        series = items[0]
        user_id = self._jellyfin._auth.user_id or ""
        latest = await self._jellyfin.async_get_latest_episode(series.id, user_id)
        if not latest:
            result.speech_reply = f"No episodes found for {series.name}."
            return result
        ep_id, ep_name = latest
        sessions = await self._jellyfin.async_get_sessions()
        session = next(iter(sessions), None)
        if not session:
            result.speech_reply = "No active player session found."
            return result
        await self._ensure_tv_awake()
        await self._jellyfin.async_play(session.id, ep_id)
        result.media_title = ep_name
        result.speech_reply = result.speech_reply or f"Playing the latest: {ep_name}."
        return result

    async def _handle_next_episode(self, result: IntentResult) -> IntentResult:
        if not self._jellyfin:
            return result
        session_id = await self._active_session_id()
        if not session_id:
            result.speech_reply = "Nothing is playing."
            return result
        await self._jellyfin.async_next_track(session_id)
        result.speech_reply = result.speech_reply or "Skipping to the next episode."
        return result

    async def _handle_skip_intro(self, result: IntentResult) -> IntentResult:
        if not self._jellyfin:
            return result
        session_id = await self._active_session_id()
        if not session_id:
            result.speech_reply = "Nothing is playing."
            return result
        skipped = await self._jellyfin.async_skip_intro(session_id)
        result.speech_reply = result.speech_reply or ("Skipped intro." if skipped else "Couldn't find the intro.")
        return result

    async def _handle_quality(self, result: IntentResult, direction: int) -> IntentResult:
        """Step bitrate up (+1) or down (-1) and restart playback with the new cap."""
        if not self._jellyfin:
            return result
        sessions = await self._jellyfin.async_get_sessions()
        active = next((s for s in sessions if s.item), None)
        if not active:
            result.speech_reply = "Nothing is playing."
            return result

        # Move index
        if self._bitrate_idx < 0:
            # Currently auto — start from top or bottom depending on direction
            self._bitrate_idx = len(self._bitrate_presets) - 1 if direction < 0 else 0
        else:
            self._bitrate_idx = max(0, min(len(self._bitrate_presets) - 1, self._bitrate_idx + direction))

        bitrate = self._bitrate_presets[self._bitrate_idx]
        item_id = active.item.id  # type: ignore[union-attr]
        pos = active.position_ticks

        await self._jellyfin.async_stop(active.id)
        await self._jellyfin.async_play(active.id, item_id, start_ticks=pos, max_bitrate_kbps=bitrate)

        label = f"{bitrate // 1000} Mbps" if bitrate >= 1000 else f"{bitrate} kbps"
        result.speech_reply = result.speech_reply or f"Quality set to {label}."
        return result

    async def _handle_favorite(self, result: IntentResult, add: bool) -> IntentResult:
        if not self._jellyfin:
            return result
        sessions = await self._jellyfin.async_get_sessions()
        active = next((s for s in sessions if s.item), None)
        if not active or not active.item:
            result.speech_reply = "Nothing is playing to favorite."
            return result
        user_id = self._jellyfin._auth.user_id or ""
        await self._jellyfin.async_set_favorite(user_id, active.item.id, is_favorite=add)
        action = "Added to" if add else "Removed from"
        result.speech_reply = result.speech_reply or f"{action} favorites: {active.item.name}."
        return result

    async def _handle_now_playing(self, result: IntentResult) -> IntentResult:
        if not self._jellyfin:
            return result
        sessions = await self._jellyfin.async_get_sessions()
        active = next((s for s in sessions if s.item and not s.is_paused), None)
        if not active:
            active = next((s for s in sessions if s.item), None)
        if not active or not active.item:
            result.speech_reply = "Nothing is currently playing."
            return result
        name = active.item.name
        paused = " (paused)" if active.is_paused else ""
        result.speech_reply = result.speech_reply or f"Now playing: {name}{paused}."
        return result

    async def _handle_open_app(self, result: IntentResult) -> IntentResult:
        if not self._tv:
            result.speech_reply = "No TV is configured."
            return result
        awake = await self._ensure_tv_awake()
        if not awake:
            result.speech_reply = "Couldn't wake the TV. Is it connected?"
            return result
        launched = await self._tv.async_launch_app(self._preferred_client_package)
        if launched:
            result.speech_reply = result.speech_reply or "Opening Jellyfin."
        else:
            result.speech_reply = "Couldn't open Jellyfin — is the app installed?"
        return result

    async def _ensure_tv_awake(self) -> bool:
        """Wake TV before sending playback commands. No-op if no TV configured."""
        import inspect
        if not self._tv:
            return True
        ensure_fn = getattr(self._tv, "async_ensure_awake", None)
        if ensure_fn and inspect.iscoroutinefunction(ensure_fn):
            return await ensure_fn()
        wake_fn = getattr(self._tv, "async_wake", None)
        if wake_fn and inspect.iscoroutinefunction(wake_fn):
            await wake_fn()
        return True

    async def _active_session_id(self) -> Optional[str]:
        if not self._jellyfin:
            return None
        sessions = await self._jellyfin.async_get_sessions()
        active = next((s for s in sessions if s.item), None)
        return active.id if active else None

    async def _send_key(self, key: str) -> None:
        if self._tv:
            await self._tv.async_send_key(key)
        else:
            _LOGGER.debug("No TV controller configured; key %s ignored", key)

    _PLAY_PREFIXES = ("play ", "put on ", "watch ", "start ")
    _SEARCH_PREFIXES = ("search for ", "search ", "find ", "look up ", "show me ")
    _PAUSE_PHRASES = frozenset({"pause", "pause it", "pause playback", "pause the show", "pause the movie"})
    _STOP_PHRASES = frozenset({"stop", "stop it", "stop playback", "stop playing", "stop the show", "stop the movie"})
    _RESUME_PHRASES = frozenset({"resume", "continue", "unpause", "keep watching", "continue watching", "resume playback", "resume what i was watching"})
    _NEXT_EP_PHRASES = frozenset({"next episode", "next ep", "skip episode", "next"})
    _SKIP_INTRO_PHRASES = frozenset({"skip intro", "skip the intro", "skip opening"})
    _QUALITY_DOWN_PHRASES = frozenset({"lower quality", "lower the quality", "reduce quality", "worse quality", "buffering", "it's buffering", "lower bitrate"})
    _QUALITY_UP_PHRASES = frozenset({"higher quality", "better quality", "increase quality", "raise quality", "higher bitrate"})
    _FAVORITE_PHRASES = frozenset({"favorite", "add to favorites", "add this to favorites", "mark as favorite"})
    _UNFAVORITE_PHRASES = frozenset({"unfavorite", "remove from favorites", "remove this from favorites"})
    _NOW_PLAYING_PHRASES = frozenset({"what's playing", "whats playing", "what is playing", "now playing", "what's on"})
    _OPEN_APP_PHRASES = frozenset({"open jellyfin", "launch jellyfin", "open the app", "launch the app"})
    _NAVIGATE_PHRASES: dict[str, str] = {
        "up": "up", "go up": "up", "move up": "up", "scroll up": "up",
        "down": "down", "go down": "down", "move down": "down", "scroll down": "down",
        "left": "left", "go left": "left", "move left": "left",
        "right": "right", "go right": "right", "move right": "right",
        "back": "back", "go back": "back",
        "home": "home", "go home": "home",
        "select": "select", "ok": "select", "enter": "select", "confirm": "select",
        "page up": "page_up", "page down": "page_down",
        "fast forward": "fast_forward", "rewind": "rewind",
        "volume up": "volume_up", "volume down": "volume_down", "mute": "mute",
    }

    def _rule_based_intent(self, text: str) -> IntentResult:
        """Map a voice command to an intent without an AI provider."""
        stripped = text.strip()
        lower = stripped.lower()
        if lower in self._PAUSE_PHRASES:
            return IntentResult(intent="PAUSE")
        if lower in self._STOP_PHRASES:
            return IntentResult(intent="STOP")
        if lower in self._RESUME_PHRASES:
            return IntentResult(intent="RESUME")
        if lower in self._NEXT_EP_PHRASES:
            return IntentResult(intent="NEXT_EPISODE")
        if lower in self._SKIP_INTRO_PHRASES:
            return IntentResult(intent="SKIP_INTRO")
        if lower in self._QUALITY_DOWN_PHRASES:
            return IntentResult(intent="QUALITY_DOWN")
        if lower in self._QUALITY_UP_PHRASES:
            return IntentResult(intent="QUALITY_UP")
        if lower in self._FAVORITE_PHRASES:
            return IntentResult(intent="FAVORITE")
        if lower in self._UNFAVORITE_PHRASES:
            return IntentResult(intent="UNFAVORITE")
        if lower in self._NOW_PLAYING_PHRASES:
            return IntentResult(intent="NOW_PLAYING")
        if lower in self._OPEN_APP_PHRASES:
            return IntentResult(intent="OPEN_APP")
        if lower in self._NAVIGATE_PHRASES:
            return IntentResult(intent="NAVIGATE", params={"direction": self._NAVIGATE_PHRASES[lower]})
        for prefix in self._PLAY_PREFIXES:
            if lower.startswith(prefix):
                return IntentResult(intent="PLAY", params={"query": stripped[len(prefix):].strip()})
        for prefix in self._SEARCH_PREFIXES:
            if lower.startswith(prefix):
                return IntentResult(intent="SEARCH", params={"query": stripped[len(prefix):].strip()})
        return IntentResult(intent="SEARCH", params={"query": stripped})
