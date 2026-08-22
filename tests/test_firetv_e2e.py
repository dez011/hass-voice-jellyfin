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

    def __init__(
        self,
        ai_enabled: bool = False,
        ai_provider=None,
        target_device: str = "",
        entity_id: str = FIRE_TV_ENTITY,
        entry_id: str = "e2e-entry",
        shared_jellyfin=None,
        default_user: str = "",
    ):
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
        entry.entry_id = entry_id
        entry.data = {
            **ENTRY_DATA, "ai_enabled": ai_enabled,
            "android_tv_entity": entity_id, "jellyfin_target_device": target_device,
            # ENTRY_DATA's "jellyfin_default_user" is a fixed test fixture
            # value (only meaningful for auth before user-scoped session
            # targeting existed). Override to blank by default so harnesses
            # built for device-targeting tests aren't accidentally also
            # user-filtered; tests of user targeting pass default_user
            # explicitly.
            "jellyfin_default_user": default_user,
        }
        entry.options = {}
        self.entry = entry

        # Fake Jellyfin server. Pass shared_jellyfin (with its own
        # async_get_sessions covering multiple devices) so two harnesses can
        # represent two TVs/entries pointed at the SAME physical server —
        # the scenario device targeting exists for.
        self.now_playing_session = PlaybackSession(
            id="sess-1", user_id="user-1",
            item=MediaItem(id="item-now", name="Something", type="Movie"),
            position_ticks=0, is_paused=False,
        )
        if shared_jellyfin is not None:
            jf = shared_jellyfin
        else:
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
        coordinator.tv_controller = AndroidTVController(hass, entity_id)
        coordinator.navigation_mode = NavigationMode(hass, entry, coordinator)
        # Harness builds the coordinator directly (skips async_setup), so
        # mirror what async_setup would have read from config.
        coordinator._target_device = target_device
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


# ---------------------------------------------------------------------------
# Two TVs, one Jellyfin server — the multi-household scenario
# ---------------------------------------------------------------------------

def _shared_two_device_server():
    """One Jellyfin server with two active sessions: yours and your
    brother's, on different TVs."""
    sess_living_room = PlaybackSession(
        id="sess-living-room", user_id="user-1",
        item=MediaItem(id="item-a", name="The Dark Knight", type="Movie"),
        device_name="Living Room Fire TV", client="Jellyfin Android TV",
    )
    sess_bedroom = PlaybackSession(
        id="sess-bedroom", user_id="user-2",
        item=MediaItem(id="item-b", name="Bluey", type="Series"),
        device_name="Bedroom Fire TV", client="Astra",
    )
    jf = MagicMock()
    jf.async_get_sessions = AsyncMock(return_value=[sess_living_room, sess_bedroom])
    jf.async_play = AsyncMock()
    jf.async_pause = AsyncMock()
    jf.async_stop = AsyncMock()
    jf.async_search = AsyncMock(return_value=[])
    jf._auth = MagicMock()
    jf._auth.user_id = "user-1"
    return jf, sess_living_room, sess_bedroom


@pytest.mark.asyncio
async def test_two_tvs_pause_targets_only_their_own_session():
    """The scenario this feature exists for: two people, two Fire TVs, one
    Jellyfin server. Pausing from one entry must never touch the other's."""
    shared_jf, sess_a, sess_b = _shared_two_device_server()
    tv_a = FireTVHarness(
        target_device="Living Room", entity_id="media_player.living_room",
        entry_id="entry-a", shared_jellyfin=shared_jf,
    )
    tv_b = FireTVHarness(
        target_device="Bedroom", entity_id="media_player.bedroom",
        entry_id="entry-b", shared_jellyfin=shared_jf,
    )

    await tv_a.say("pause")
    shared_jf.async_pause.assert_awaited_once_with("sess-living-room")

    shared_jf.async_pause.reset_mock()
    await tv_b.say("pause")
    shared_jf.async_pause.assert_awaited_once_with("sess-bedroom")


@pytest.mark.asyncio
async def test_two_tvs_stop_targets_only_their_own_session():
    shared_jf, sess_a, sess_b = _shared_two_device_server()
    tv_a = FireTVHarness(
        target_device="Living Room", entity_id="media_player.living_room",
        entry_id="entry-a", shared_jellyfin=shared_jf,
    )
    tv_b = FireTVHarness(
        target_device="Bedroom", entity_id="media_player.bedroom",
        entry_id="entry-b", shared_jellyfin=shared_jf,
    )

    await tv_b.say("stop")
    shared_jf.async_stop.assert_awaited_once_with("sess-bedroom")
    shared_jf.async_stop.reset_mock()

    await tv_a.say("stop")
    shared_jf.async_stop.assert_awaited_once_with("sess-living-room")


@pytest.mark.asyncio
async def test_two_tvs_play_targets_only_their_own_session():
    shared_jf, sess_a, sess_b = _shared_two_device_server()
    item = MediaItem(id="item-new", name="Interstellar", type="Movie")
    shared_jf.async_search = AsyncMock(return_value=[item])
    tv_a = FireTVHarness(
        target_device="Living Room", entity_id="media_player.living_room",
        entry_id="entry-a", shared_jellyfin=shared_jf,
    )

    await tv_a.say("play interstellar")
    shared_jf.async_play.assert_awaited_once_with("sess-living-room", "item-new", start_ticks=0)


@pytest.mark.asyncio
async def test_untargeted_tv_without_device_filter_still_works_alone():
    """A single-TV household (no target_device configured) keeps the
    original simple behavior — first session found."""
    shared_jf, sess_a, sess_b = _shared_two_device_server()
    tv = FireTVHarness(shared_jellyfin=shared_jf)  # no target_device
    await tv.say("pause")
    shared_jf.async_pause.assert_awaited_once_with("sess-living-room")


@pytest.mark.asyncio
async def test_default_user_scopes_commands_to_that_persons_session():
    """Two people share one Jellyfin server/device pool with no per-TV device
    targeting configured — commands must still land on the configured
    person's own session, not whichever session /Sessions lists first.
    """
    shared_jf, sess_a, sess_b = _shared_two_device_server()
    # No target_device for either — only jellyfin_default_user distinguishes
    # who each entry's commands should act on.
    person_1 = FireTVHarness(entry_id="entry-1", shared_jellyfin=shared_jf, default_user="user-1")
    person_2 = FireTVHarness(entry_id="entry-2", shared_jellyfin=shared_jf, default_user="user-2")

    await person_2.say("pause")
    shared_jf.async_pause.assert_awaited_once_with("sess-bedroom")

    shared_jf.async_pause.reset_mock()
    await person_1.say("pause")
    shared_jf.async_pause.assert_awaited_once_with("sess-living-room")


@pytest.mark.asyncio
async def test_now_playing_sensor_data_isolated_per_tv():
    """coordinator._async_update_data() for each entry must only surface
    its own TV's now-playing info, not whichever session Jellyfin lists
    first — this is what feeds the Now Playing sensor per config entry."""
    shared_jf, sess_a, sess_b = _shared_two_device_server()
    tv_a = FireTVHarness(
        target_device="Living Room", entity_id="media_player.living_room",
        entry_id="entry-a", shared_jellyfin=shared_jf,
    )
    tv_b = FireTVHarness(
        target_device="Bedroom", entity_id="media_player.bedroom",
        entry_id="entry-b", shared_jellyfin=shared_jf,
    )

    data_a = await tv_a.coordinator._async_update_data()
    data_b = await tv_b.coordinator._async_update_data()

    assert data_a["now_playing"]["title"] == "The Dark Knight"
    assert data_a["now_playing"]["device"] == "Living Room Fire TV"
    assert data_b["now_playing"]["title"] == "Bluey"
    assert data_b["now_playing"]["device"] == "Bedroom Fire TV"
    assert data_b["now_playing"]["client"] == "Astra"
