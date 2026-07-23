"""Mocked integration tests for Fire TV / AndroidTV flows.

Covers the full stack from IntentRouter → AndroidTVController → HA service
calls and ADB fallback, without needing a physical device.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.voice_jellyfin.tv.android_tv import AndroidTVController
from custom_components.voice_jellyfin.tv.deep_link import (
    JELLYFIN_PACKAGE,
    async_launch_jellyfin,
)
from custom_components.voice_jellyfin.tv.adb import ADBController
from custom_components.voice_jellyfin.const import (
    KEY_UP, KEY_DOWN, KEY_SELECT, KEY_BACK, KEY_HOME,
    KEY_PLAY, KEY_PAUSE, KEY_FAST_FORWARD, KEY_REWIND,
)

ENTITY_ID = "media_player.fire_tv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hass_with_androidtv(async_call_mock: AsyncMock | None = None) -> MagicMock:
    """Return a mock hass where the androidtv integration is available."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=True)
    hass.services.async_call = async_call_mock or AsyncMock(return_value=None)
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    return hass


def _hass_without_androidtv(async_call_mock: AsyncMock | None = None) -> MagicMock:
    """Return a mock hass where only media_player services exist."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_call = async_call_mock or AsyncMock(return_value=None)
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    return hass


def _tv_state(state: str) -> MagicMock:
    s = MagicMock()
    s.state = state
    return s


# ---------------------------------------------------------------------------
# _adb_command return type (regression for the None crash fix)
# ---------------------------------------------------------------------------

class TestAdbCommandReturnType:
    @pytest.mark.asyncio
    async def test_returns_empty_string_on_success(self):
        """_adb_command must return str, never None."""
        hass = _hass_with_androidtv()
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl._adb_command("input keyevent 0")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_returns_error_string_when_service_raises(self):
        """_adb_command returns 'error' string when HA service call raises."""
        hass = _hass_with_androidtv(AsyncMock(side_effect=Exception("ADB failed")))
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl._adb_command("am start org.jellyfin.androidtv")
        assert result == "error"

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_androidtv_unavailable(self):
        """_adb_command returns '' (not None) when androidtv service is missing."""
        hass = _hass_without_androidtv()
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl._adb_command("am start org.jellyfin.androidtv")
        assert isinstance(result, str)
        assert result == ""


# ---------------------------------------------------------------------------
# async_launch_app
# ---------------------------------------------------------------------------

class TestLaunchApp:
    @pytest.mark.asyncio
    async def test_ha_select_source_succeeds(self):
        """select_source succeeds → returns True without calling ADB."""
        hass = _hass_with_androidtv()
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl.async_launch_app(JELLYFIN_PKG := "org.jellyfin.androidtv")
        assert result is True
        # select_source should have been tried
        call_args_list = hass.services.async_call.call_args_list
        services_called = [(c[0][0], c[0][1]) for c in call_args_list]
        assert ("media_player", "select_source") in services_called

    @pytest.mark.asyncio
    async def test_ha_select_source_fails_falls_back_to_adb(self):
        """select_source raises → falls back to ADB _adb_command."""
        call_count = {"n": 0}

        async def _side_effect(domain, service, data, **kwargs):
            if service == "select_source":
                raise Exception("not supported")
            # ADB call succeeds
            return None

        hass = _hass_with_androidtv(AsyncMock(side_effect=_side_effect))
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl.async_launch_app("org.jellyfin.androidtv")
        assert result is True

    @pytest.mark.asyncio
    async def test_adb_reports_error_returns_false(self):
        """select_source fails, ADB returns error text → returns False."""
        async def _side_effect(domain, service, data, **kwargs):
            if service == "select_source":
                raise Exception("not supported")
            # adb_command "succeeds" but TV says error
            raise Exception("error: Activity not started")

        hass = _hass_with_androidtv(AsyncMock(side_effect=_side_effect))
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl.async_launch_app("org.jellyfin.androidtv")
        # _adb_command returns "error" on exception → async_launch_app returns False
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_package_still_attempts_launch(self):
        """Unknown package name still calls select_source without crashing."""
        hass = _hass_with_androidtv()
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl.async_launch_app("com.example.unknown")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# async_deep_link
# ---------------------------------------------------------------------------

class TestDeepLink:
    @pytest.mark.asyncio
    async def test_deep_link_success(self):
        """ADB command succeeds → returns True."""
        hass = _hass_with_androidtv()
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl.async_deep_link("jellyfin://openItem?id=abc123")
        assert result is True

    @pytest.mark.asyncio
    async def test_deep_link_with_package(self):
        """Package flag is included in the ADB command."""
        hass = _hass_with_androidtv()
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl.async_deep_link(
            "jellyfin://openItem?id=abc123",
            package="org.jellyfin.mobile",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_deep_link_adb_exception_returns_false(self):
        """Exception during ADB call → returns False without raising."""
        hass = _hass_with_androidtv(AsyncMock(side_effect=Exception("connection reset")))
        ctrl = AndroidTVController(hass, ENTITY_ID)
        result = await ctrl.async_deep_link("jellyfin://openItem?id=abc123")
        assert result is False

    @pytest.mark.asyncio
    async def test_deep_link_uri_included_in_command(self):
        """The URI is passed through to the underlying ADB command."""
        captured = {}

        async def _capture(domain, service, data, **kwargs):
            captured["data"] = data

        hass = _hass_with_androidtv(AsyncMock(side_effect=_capture))
        ctrl = AndroidTVController(hass, ENTITY_ID)
        await ctrl.async_deep_link("jellyfin://openItem?id=item-999")

        cmd = captured.get("data", {}).get("command", "")
        assert "item-999" in cmd


# ---------------------------------------------------------------------------
# async_ensure_awake
# ---------------------------------------------------------------------------

class TestEnsureAwake:
    @pytest.mark.asyncio
    async def test_tv_already_on_returns_true_immediately(self):
        """TV is already playing — should return True on first state check."""
        hass = _hass_with_androidtv()
        hass.states.get = MagicMock(return_value=_tv_state("playing"))

        ctrl = AndroidTVController(hass, ENTITY_ID)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await ctrl.async_ensure_awake(timeout=10.0)

        assert result is True
        mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tv_wakes_after_two_polls(self):
        """TV is off, then transitions to idle after 2 polls → returns True."""
        states = [_tv_state("off"), _tv_state("off"), _tv_state("idle")]
        state_iter = iter(states)
        hass = _hass_with_androidtv()
        hass.states.get = MagicMock(side_effect=lambda _: next(state_iter, _tv_state("idle")))

        ctrl = AndroidTVController(hass, ENTITY_ID)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await ctrl.async_ensure_awake(timeout=30.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_tv_never_wakes_returns_false(self):
        """TV stays 'off' for the entire timeout → returns False."""
        hass = _hass_with_androidtv()
        hass.states.get = MagicMock(return_value=_tv_state("off"))

        ctrl = AndroidTVController(hass, ENTITY_ID)

        # Pin loop time so deadline expires after first check
        fake_time = [0.0]

        def _fake_time():
            t = fake_time[0]
            fake_time[0] += 20.0  # advance 20s each call
            return t

        with patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.time = _fake_time
            result = await ctrl.async_ensure_awake(timeout=5.0)

        assert result is False

    @pytest.mark.asyncio
    async def test_androidtv_adb_ping_returns_true_early(self):
        """If androidtv ADB probe succeeds, return True even if state is unknown."""
        hass = _hass_with_androidtv()
        hass.states.get = MagicMock(return_value=_tv_state("unknown"))

        ctrl = AndroidTVController(hass, ENTITY_ID)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await ctrl.async_ensure_awake(timeout=30.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_wake_called_before_polling(self):
        """async_wake() must be called before polling starts."""
        hass = _hass_with_androidtv()
        hass.states.get = MagicMock(return_value=_tv_state("playing"))

        ctrl = AndroidTVController(hass, ENTITY_ID)
        ctrl.async_wake = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await ctrl.async_ensure_awake(timeout=10.0)

        ctrl.async_wake.assert_awaited_once()


# ---------------------------------------------------------------------------
# async_wake
# ---------------------------------------------------------------------------

class TestWake:
    @pytest.mark.asyncio
    async def test_wake_uses_androidtv_wakeup_when_available(self):
        """WAKEUP command sent via androidtv.adb_command when service exists."""
        hass = _hass_with_androidtv()
        ctrl = AndroidTVController(hass, ENTITY_ID)
        await ctrl.async_wake()

        hass.services.async_call.assert_awaited_once()
        domain, service, data = hass.services.async_call.call_args[0][:3]
        assert domain == "androidtv"
        assert service == "adb_command"
        assert data.get("command") == "WAKEUP"

    @pytest.mark.asyncio
    async def test_wake_falls_back_to_turn_on(self):
        """When androidtv unavailable, falls back to media_player.turn_on."""
        hass = _hass_without_androidtv()
        ctrl = AndroidTVController(hass, ENTITY_ID)
        await ctrl.async_wake()

        hass.services.async_call.assert_awaited_once()
        domain, service = hass.services.async_call.call_args[0][:2]
        assert domain == "media_player"
        assert service == "turn_on"

    @pytest.mark.asyncio
    async def test_wake_androidtv_fails_no_exception_raised(self):
        """androidtv.adb_command raises → no crash, just debug log."""
        hass = _hass_with_androidtv(AsyncMock(side_effect=Exception("adb offline")))
        ctrl = AndroidTVController(hass, ENTITY_ID)
        await ctrl.async_wake()  # must not raise


# ---------------------------------------------------------------------------
# deep_link.async_launch_jellyfin
# ---------------------------------------------------------------------------

class TestDeepLinkHelper:
    @pytest.mark.asyncio
    async def test_launch_home_screen(self):
        """No item_id → MAIN/LAUNCHER intent, not a deep link URI."""
        adb = MagicMock()
        adb.async_send_command = AsyncMock(return_value="")

        result = await async_launch_jellyfin(adb)

        assert result is True
        cmd = adb.async_send_command.call_args[0][0]
        assert "MAIN" in cmd
        assert JELLYFIN_PACKAGE in cmd
        assert "openItem" not in cmd

    @pytest.mark.asyncio
    async def test_launch_specific_item(self):
        """item_id present → VIEW intent with jellyfin://openItem?id= URI."""
        adb = MagicMock()
        adb.async_send_command = AsyncMock(return_value="")

        result = await async_launch_jellyfin(adb, item_id="item-abc-123")

        assert result is True
        cmd = adb.async_send_command.call_args[0][0]
        assert "openItem" in cmd
        assert "item-abc-123" in cmd
        assert "VIEW" in cmd

    @pytest.mark.asyncio
    async def test_launch_mobile_package(self):
        """org.jellyfin.mobile uses its own activity name."""
        adb = MagicMock()
        adb.async_send_command = AsyncMock(return_value="")

        await async_launch_jellyfin(adb, package="org.jellyfin.mobile")

        cmd = adb.async_send_command.call_args[0][0]
        assert "org.jellyfin.mobile" in cmd
        assert "MainActivity" in cmd

    @pytest.mark.asyncio
    async def test_launch_returns_false_on_error_output(self):
        """ADB output contains 'error' → returns False."""
        adb = MagicMock()
        adb.async_send_command = AsyncMock(
            return_value="Error type 3\nError: Activity class not found"
        )

        result = await async_launch_jellyfin(adb, item_id="bad-item")
        assert result is False

    @pytest.mark.asyncio
    async def test_launch_returns_false_on_exception_output(self):
        """ADB output contains 'exception' → returns False."""
        adb = MagicMock()
        adb.async_send_command = AsyncMock(
            return_value="java.lang.RuntimeException: ..."
        )
        result = await async_launch_jellyfin(adb)
        assert result is False

    @pytest.mark.asyncio
    async def test_launch_unknown_package_uses_fallback_activity(self):
        """Unknown package → activity name derived from package + .ui.startup.StartupActivity."""
        adb = MagicMock()
        adb.async_send_command = AsyncMock(return_value="")

        await async_launch_jellyfin(adb, package="com.custom.jellyfin")

        cmd = adb.async_send_command.call_args[0][0]
        assert "com.custom.jellyfin" in cmd
        assert "StartupActivity" in cmd


# ---------------------------------------------------------------------------
# IntentRouter → FireTV integration
# ---------------------------------------------------------------------------

class TestIntentRouterFireTV:
    """End-to-end: voice command → IntentRouter → AndroidTVController → HA services."""

    def _make_router(self, hass, jellyfin_client=None):
        from custom_components.voice_jellyfin.ai.intent_router import IntentRouter
        from custom_components.voice_jellyfin.jellyfin.models import PlaybackSession, MediaItem

        if jellyfin_client is None:
            jellyfin_client = MagicMock()
            jellyfin_client.async_get_sessions = AsyncMock(return_value=[
                PlaybackSession(
                    id="sess-001",
                    user_id="uid",
                    item=MediaItem(id="item-001", name="Breaking Bad", type="Episode"),
                    position_ticks=0,
                    is_paused=False,
                )
            ])
            jellyfin_client.async_play = AsyncMock()
            jellyfin_client.async_pause = AsyncMock()
            jellyfin_client.async_stop = AsyncMock()
            jellyfin_client.async_search = AsyncMock(return_value=[
                MediaItem(id="item-002", name="The Dark Knight", type="Movie")
            ])
            jellyfin_client.catalog = MagicMock()
            jellyfin_client.catalog.search = MagicMock(
                return_value=[MediaItem(id="item-002", name="The Dark Knight", type="Movie")]
            )
            jellyfin_client._auth = MagicMock()
            jellyfin_client._auth.user_id = "uid"

        tv = AndroidTVController(hass, ENTITY_ID)
        return IntentRouter(
            jellyfin=jellyfin_client,
            tv=tv,
            nav=None,
            hass=hass,
            tv_type="android_tv",
            preferred_client_package=JELLYFIN_PACKAGE,
            bitrate_presets=[1000, 4000, 8000],
            current_bitrate_idx=-1,
        )

    @pytest.mark.asyncio
    async def test_navigate_up_sends_key_via_androidtv(self):
        """NAVIGATE UP intent reaches androidtv.adb_command with keycode 19."""
        hass = _hass_with_androidtv()
        router = self._make_router(hass)

        from custom_components.voice_jellyfin.ai.context import AIContext
        from custom_components.voice_jellyfin.ai.base import AIProvider
        import json

        class _NavProvider(AIProvider):
            @property
            def name(self): return "mock"
            async def async_query(self, messages, system_prompt):
                return json.dumps({"intent": "NAVIGATE", "params": {"direction": "up"}, "speech": ""})

        await router.async_route("go up", _NavProvider(), AIContext(), ai_enabled=True)

        calls = hass.services.async_call.call_args_list
        key_calls = [c for c in calls if c[0][0] == "androidtv" and "keyevent" in c[0][2].get("command", "")]
        assert len(key_calls) >= 1
        assert "19" in key_calls[0][0][2]["command"]  # keycode for UP

    @pytest.mark.asyncio
    async def test_navigate_select_sends_keycode_23(self):
        """NAVIGATE SELECT → keycode 23 (DPAD_CENTER)."""
        hass = _hass_with_androidtv()
        router = self._make_router(hass)

        from custom_components.voice_jellyfin.ai.context import AIContext
        import json

        class _SelectProvider:
            @property
            def name(self): return "mock"
            async def async_query(self, messages, system_prompt):
                return json.dumps({"intent": "SELECT", "params": {}, "speech": ""})

        await router.async_route("select", _SelectProvider(), AIContext(), ai_enabled=True)

        calls = hass.services.async_call.call_args_list
        key_calls = [c for c in calls if c[0][0] == "androidtv" and "keyevent 23" in c[0][2].get("command", "")]
        assert len(key_calls) >= 1

    @pytest.mark.asyncio
    async def test_scroll_down_three_times(self):
        """SCROLL down amount=3 sends 3 separate key events."""
        hass = _hass_with_androidtv()
        router = self._make_router(hass)

        from custom_components.voice_jellyfin.ai.context import AIContext
        import json

        class _ScrollProvider:
            @property
            def name(self): return "mock"
            async def async_query(self, messages, system_prompt):
                return json.dumps({"intent": "SCROLL", "params": {"direction": "down", "amount": 3}, "speech": ""})

        await router.async_route("scroll down 3", _ScrollProvider(), AIContext(), ai_enabled=True)

        calls = hass.services.async_call.call_args_list
        key_calls = [c for c in calls if c[0][0] == "androidtv" and "keyevent" in c[0][2].get("command", "")]
        assert len(key_calls) == 3

    @pytest.mark.asyncio
    async def test_scroll_with_non_integer_amount_defaults_to_1(self):
        """SCROLL with AI returning non-int amount → treated as 1, no crash."""
        hass = _hass_with_androidtv()
        router = self._make_router(hass)

        from custom_components.voice_jellyfin.ai.context import AIContext
        import json

        class _BadAmountProvider:
            @property
            def name(self): return "mock"
            async def async_query(self, messages, system_prompt):
                return json.dumps({"intent": "SCROLL", "params": {"direction": "down", "amount": "a lot"}, "speech": ""})

        result = await router.async_route("scroll down a lot", _BadAmountProvider(), AIContext(), ai_enabled=True)
        # Should not crash, should send exactly 1 key event
        calls = hass.services.async_call.call_args_list
        key_calls = [c for c in calls if c[0][0] == "androidtv" and "keyevent" in c[0][2].get("command", "")]
        assert len(key_calls) == 1

    @pytest.mark.asyncio
    async def test_open_app_intent_calls_launch_app(self):
        """OPEN_APP intent → async_launch_app called with Jellyfin package."""
        hass = _hass_with_androidtv()
        router = self._make_router(hass)

        from custom_components.voice_jellyfin.ai.context import AIContext
        import json

        class _OpenAppProvider:
            @property
            def name(self): return "mock"
            async def async_query(self, messages, system_prompt):
                return json.dumps({"intent": "OPEN_APP", "params": {"app": "jellyfin"}, "speech": "Opening Jellyfin."})

        result = await router.async_route("open jellyfin", _OpenAppProvider(), AIContext(), ai_enabled=True)

        # select_source or adb_command should have been called
        assert hass.services.async_call.await_count >= 1

    @pytest.mark.asyncio
    async def test_no_tv_configured_navigate_returns_gracefully(self):
        """NAVIGATE with no TV controller doesn't crash — just logs and returns."""
        from custom_components.voice_jellyfin.ai.intent_router import IntentRouter
        from custom_components.voice_jellyfin.ai.context import AIContext
        import json

        router = IntentRouter(
            jellyfin=MagicMock(),
            tv=None,
            nav=None,
            hass=MagicMock(),
            tv_type="",
            preferred_client_package=JELLYFIN_PACKAGE,
            bitrate_presets=[1000],
            current_bitrate_idx=-1,
        )

        class _NavProvider:
            @property
            def name(self): return "mock"
            async def async_query(self, messages, system_prompt):
                return json.dumps({"intent": "NAVIGATE", "params": {"direction": "up"}, "speech": ""})

        result = await router.async_route("go up", _NavProvider(), AIContext(), ai_enabled=True)
        assert result is not None  # returned an IntentResult, didn't crash

    @pytest.mark.asyncio
    async def test_rule_based_navigate_up_without_ai(self):
        """Without AI, rule-based routing sends UP key for 'go up'."""
        hass = _hass_with_androidtv()
        router = self._make_router(hass)

        from custom_components.voice_jellyfin.ai.context import AIContext

        await router.async_route("go up", None, AIContext(), ai_enabled=False)

        calls = hass.services.async_call.call_args_list
        key_calls = [c for c in calls if c[0][0] == "androidtv" and "19" in c[0][2].get("command", "")]
        assert len(key_calls) >= 1

    @pytest.mark.asyncio
    async def test_rule_based_navigate_back_without_ai(self):
        """Without AI, 'go back' sends BACK key (keycode 4)."""
        hass = _hass_with_androidtv()
        router = self._make_router(hass)

        from custom_components.voice_jellyfin.ai.context import AIContext

        await router.async_route("go back", None, AIContext(), ai_enabled=False)

        calls = hass.services.async_call.call_args_list
        key_calls = [c for c in calls if c[0][0] == "androidtv" and "4" in c[0][2].get("command", "")]
        assert len(key_calls) >= 1

    @pytest.mark.asyncio
    async def test_pause_targets_active_session_not_idle(self):
        """PAUSE picks the session with an active item, not the first idle session."""
        from custom_components.voice_jellyfin.jellyfin.models import PlaybackSession, MediaItem

        idle_session = PlaybackSession(id="idle-001", user_id="uid", item=None, position_ticks=0, is_paused=False)
        active_session = PlaybackSession(
            id="active-001", user_id="uid",
            item=MediaItem(id="item-001", name="Interstellar", type="Movie"),
            position_ticks=5_000_000, is_paused=False,
        )

        jellyfin = MagicMock()
        jellyfin.async_get_sessions = AsyncMock(return_value=[idle_session, active_session])
        jellyfin.async_pause = AsyncMock()
        jellyfin.catalog = MagicMock()
        jellyfin._auth = MagicMock()
        jellyfin._auth.user_id = "uid"

        hass = _hass_with_androidtv()
        router = self._make_router(hass, jellyfin_client=jellyfin)

        from custom_components.voice_jellyfin.ai.context import AIContext
        import json

        class _PauseProvider:
            @property
            def name(self): return "mock"
            async def async_query(self, messages, system_prompt):
                return json.dumps({"intent": "PAUSE", "params": {}, "speech": "Paused."})

        await router.async_route("pause", _PauseProvider(), AIContext(), ai_enabled=True)
        jellyfin.async_pause.assert_awaited_once_with("active-001")
