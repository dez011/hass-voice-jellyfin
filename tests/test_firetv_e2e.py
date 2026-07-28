"""End-to-end tests against a mock Fire TV.

These drive the REAL stack — voice_command service → coordinator voice
routing → NavigationMode / IntentRouter → AndroidTVController → the
androidtv.adb_command service — with only the edges mocked (HA service bus
and the Jellyfin HTTP client). This is the accessibility flow the
integration exists for: say the keyword once, then bare commands
("up", "right five times", "select") drive the TV until the keyword
ends the session. No AI backend is required, and an unreachable one
must not break anything.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.voice_jellyfin.const import DOMAIN
from custom_components.voice_jellyfin.coordinator import VoiceJellyfinCoordinator
from custom_components.voice_jellyfin.jellyfin.models import MediaItem, PlaybackSession

FIRE_TV_ENTITY = "media_player.fire_tv"
JELLYFIN_PKG = "org.jellyfin.androidtv"

ENTRY_DATA = {
    "jellyfin_url": "http://localhost:8096",
    "jellyfin_api_key": "key",
    "jellyfin_default_user": "user-1",
    "tv_type": "android_tv",
    "android_tv_entity": FIRE_TV_ENTITY,
    "ai_enabled": False,
    "ai_provider": "ollama",
    "nav_wake_phrase": "navigation mode",
    "nav_timeout": "0",           # never time out during tests
    "nav_confirmation_speech": True,
    "hot_mic_timeout": 0,
    "preferred_client_package": JELLYFIN_PKG,
}


class FireTVHarness:
    """Real coordinator + nav mode + Android TV controller over a fake HA bus."""

    def __init__(self, ai_enabled: bool = False, ai_provider=None):
        self.adb_commands: list[str] = []
        self.service_calls: list[tuple[str, str, dict]] = []

        hass = MagicMock()
        hass.data = {}

        async def _async_call(domain, service, data=None, blocking=False, **kw):
            data = data or {}
            self.service_calls.append((domain, service, data))
            if domain == "androidtv" and service == "adb_command":
                self.adb_commands.append(data.get("command", ""))
            return None

        hass.services.async_call = AsyncMock(side_effect=_async_call)
        hass.services.has_service = MagicMock(
            side_effect=lambda d, s: (d, s) == ("androidtv", "adb_command")
        )
        state = MagicMock()
        state.state = "on"
        hass.states.get = MagicMock(return_value=state)
        hass.bus.async_fire = MagicMock()
        hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())
        self.hass = hass

        entry = MagicMock()
        entry.entry_id = "e2e-entry"
        entry.data = {**ENTRY_DATA, "ai_enabled": ai_enabled}
        entry.options = {}
        self.entry = entry

        # Fake Jellyfin server
        self.now_playing_session = PlaybackSession(
            id="sess-1", user_id="user-1",
            item=MediaItem(id="item-now", name="Something", type="Movie"),
            position_ticks=0, is_paused=False,
        )
        jf = MagicMock()
        jf.async_get_sessions = AsyncMock(return_value=[self.now_playing_session])
        jf.async_play = AsyncMock()
        jf.async_pause = AsyncMock()
        jf.async_stop = AsyncMock()
        jf.async_search = AsyncMock(return_value=[])
        jf._auth = MagicMock()
        jf._auth.user_id = "user-1"
        self.jellyfin = jf

        # Assemble the real runtime objects
        from custom_components.voice_jellyfin.ai.context import AIContext
        from custom_components.voice_jellyfin.navigation.mode import NavigationMode
        from custom_components.voice_jellyfin.tv.android_tv import AndroidTVController

        coordinator = VoiceJellyfinCoordinator(hass, entry)
        coordinator.hass = hass
        coordinator.jellyfin_client = jf
        coordinator.ai_provider = ai_provider
        coordinator.ai_context = AIContext()
        coordinator.tv_controller = AndroidTVController(hass, FIRE_TV_ENTITY)
        coordinator.navigation_mode = NavigationMode(hass, entry, coordinator)
        self.coordinator = coordinator

        # Register the real services and grab the voice entry point
        hass.data = {DOMAIN: {entry.entry_id: coordinator}}
        registered: dict = {}
        hass.services.async_register = MagicMock(
            side_effect=lambda d, s, h, schema=None, **kw: registered.__setitem__((d, s), h)
        )
        from custom_components.voice_jellyfin.services import async_register_services
        async_register_services(hass)
        self._voice_handler = registered[(DOMAIN, "voice_command")]

    async def say(self, text: str) -> str:
        """Speak *text* through the voice_command service; return the reply."""
        call = MagicMock()
        call.data = {"text": text}
        call.return_response = True
        result = await self._voice_handler(call)
        return (result or {}).get("speech", "")

    def keyevents(self) -> list[int]:
        return [
            int(cmd.split()[-1])
            for cmd in self.adb_commands
            if cmd.startswith("input keyevent")
        ]


# ---------------------------------------------------------------------------
# The accessibility session: keyword on → bare commands → keyword off
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_navigation_session():
    """One continuous session: wake word, D-pad, volume, select, exit."""
    tv = FireTVHarness()

    reply = await tv.say("Navigation mode")
    assert tv.coordinator.navigation_mode.is_active
    assert "on" in reply.lower()

    await tv.say("up")
    await tv.say("down")
    await tv.say("right")
    await tv.say("select")
    assert tv.keyevents() == [19, 20, 22, 23]

    reply = await tv.say("exit navigation mode")
    assert not tv.coordinator.navigation_mode.is_active
    assert "off" in reply.lower()


@pytest.mark.asyncio
async def test_right_five_times_sends_five_keys():
    """'right five times' instead of saying 'right' five times."""
    tv = FireTVHarness()
    await tv.say("navigation mode")
    await tv.say("right five times")
    assert tv.keyevents() == [22, 22, 22, 22, 22]


@pytest.mark.asyncio
async def test_repeated_word_sends_multiple_keys():
    tv = FireTVHarness()
    await tv.say("navigation mode")
    await tv.say("down down down")
    assert tv.keyevents() == [20, 20, 20]


@pytest.mark.asyncio
async def test_numeric_count():
    tv = FireTVHarness()
    await tv.say("navigation mode")
    await tv.say("up 4")
    assert tv.keyevents() == [19, 19, 19, 19]


@pytest.mark.asyncio
async def test_volume_and_mute_in_nav_mode():
    tv = FireTVHarness()
    await tv.say("navigation mode")
    await tv.say("volume up")
    await tv.say("volume up two times")
    await tv.say("volume down")
    await tv.say("mute")
    assert tv.keyevents() == [24, 24, 24, 25, 164]


@pytest.mark.asyncio
async def test_volume_without_nav_mode():
    """'volume up' works outside Navigation Mode via rule-based intents."""
    tv = FireTVHarness()
    await tv.say("volume up")
    assert tv.keyevents() == [24]


@pytest.mark.asyncio
async def test_repeat_and_reverse_in_session():
    tv = FireTVHarness()
    await tv.say("navigation mode")
    await tv.say("down")
    await tv.say("again")          # repeat → down
    await tv.say("too far")        # reverse → up
    assert tv.keyevents() == [20, 20, 19]


@pytest.mark.asyncio
async def test_open_jellyfin_by_voice():
    """'open jellyfin' launches the app on the Fire TV."""
    tv = FireTVHarness()
    reply = await tv.say("open jellyfin")
    select_source = [
        c for c in tv.service_calls if c[:2] == ("media_player", "select_source")
    ]
    assert select_source and select_source[0][2]["source"] == JELLYFIN_PKG
    assert "opening" in reply.lower()


@pytest.mark.asyncio
async def test_play_exact_title_plays_immediately():
    tv = FireTVHarness()
    item = MediaItem(id="item-dk", name="The Dark Knight", type="Movie")
    tv.jellyfin.async_search = AsyncMock(return_value=[item])
    reply = await tv.say("play the dark knight")
    tv.jellyfin.async_play.assert_awaited_once_with("sess-1", "item-dk", start_ticks=0)
    assert "dark knight" in reply.lower()


@pytest.mark.asyncio
async def test_ambiguous_play_asks_then_choice_plays():
    """Multiple matches: the app asks, the user picks by ordinal."""
    tv = FireTVHarness()
    items = [
        MediaItem(id="item-dk", name="The Dark Knight", type="Movie", year=2008),
        MediaItem(id="item-bb", name="Batman Begins", type="Movie", year=2005),
    ]
    tv.jellyfin.async_search = AsyncMock(return_value=items)

    reply = await tv.say("play batman")
    tv.jellyfin.async_play.assert_not_called()
    assert "which one" in reply.lower()
    assert "The Dark Knight" in reply and "Batman Begins" in reply

    reply = await tv.say("the second one")
    tv.jellyfin.async_play.assert_awaited_once_with("sess-1", "item-bb", start_ticks=0)
    assert "batman begins" in reply.lower()


@pytest.mark.asyncio
async def test_choice_by_title_name():
    tv = FireTVHarness()
    items = [
        MediaItem(id="item-dk", name="The Dark Knight", type="Movie"),
        MediaItem(id="item-bb", name="Batman Begins", type="Movie"),
    ]
    tv.jellyfin.async_search = AsyncMock(return_value=items)
    await tv.say("play batman")
    await tv.say("batman begins")
    tv.jellyfin.async_play.assert_awaited_once_with("sess-1", "item-bb", start_ticks=0)


@pytest.mark.asyncio
async def test_non_choice_after_ambiguity_routes_normally():
    """If the user says something unrelated after being asked, the pending
    choices are dropped and the command is handled normally."""
    tv = FireTVHarness()
    items = [
        MediaItem(id="a", name="Alpha One", type="Movie"),
        MediaItem(id="b", name="Alpha Two", type="Movie"),
    ]
    tv.jellyfin.async_search = AsyncMock(return_value=items)
    await tv.say("play alpha")
    reply = await tv.say("pause")
    tv.jellyfin.async_pause.assert_awaited_once_with("sess-1")
    assert not tv.coordinator.ai_context.pending_choices


@pytest.mark.asyncio
async def test_pause_and_stop_by_voice():
    tv = FireTVHarness()
    await tv.say("pause")
    tv.jellyfin.async_pause.assert_awaited_once_with("sess-1")
    await tv.say("stop")
    tv.jellyfin.async_stop.assert_awaited_once_with("sess-1")


# ---------------------------------------------------------------------------
# AI toggle and graceful degradation
# ---------------------------------------------------------------------------

def _failing_provider():
    provider = MagicMock()
    provider.async_query = AsyncMock(side_effect=ConnectionError("Ollama unreachable"))
    return provider


@pytest.mark.asyncio
async def test_unreachable_ai_still_navigates():
    """AI enabled but Ollama down: rule-based intents keep working —
    an unreachable AI backend must never be catastrophic."""
    tv = FireTVHarness(ai_enabled=True, ai_provider=_failing_provider())
    await tv.say("navigation mode")
    await tv.say("up")
    assert tv.keyevents() == [19]


@pytest.mark.asyncio
async def test_unreachable_ai_still_plays_media():
    tv = FireTVHarness(ai_enabled=True, ai_provider=_failing_provider())
    item = MediaItem(id="item-dk", name="The Dark Knight", type="Movie")
    tv.jellyfin.async_search = AsyncMock(return_value=[item])
    reply = await tv.say("play the dark knight")
    tv.jellyfin.async_play.assert_awaited_once()
    assert "dark knight" in reply.lower()


@pytest.mark.asyncio
async def test_ai_disabled_toggle_never_queries_provider():
    """With ai_enabled False the provider is never contacted at all."""
    provider = MagicMock()
    provider.async_query = AsyncMock(return_value="{}")
    tv = FireTVHarness(ai_enabled=False, ai_provider=provider)
    await tv.say("volume up")
    provider.async_query.assert_not_called()


@pytest.mark.asyncio
async def test_working_ai_is_used_when_enabled():
    import json

    provider = MagicMock()
    provider.async_query = AsyncMock(
        return_value=json.dumps(
            {"intent": "NAVIGATE", "params": {"direction": "down"}, "speech": "Going down."}
        )
    )
    tv = FireTVHarness(ai_enabled=True, ai_provider=provider)
    reply = await tv.say("move down a bit please")
    provider.async_query.assert_awaited_once()
    assert tv.keyevents() == [20]
    assert reply == "Going down."
