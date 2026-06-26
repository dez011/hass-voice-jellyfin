"""Tests for ADB controller — mocks asyncio.create_subprocess_exec to simulate
a real Fire TV device over TCP without needing a physical device."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.voice_jellyfin.tv.adb import ADBController
from custom_components.voice_jellyfin.tv.android_tv import AndroidTVController
from custom_components.voice_jellyfin.tv.deep_link import async_launch_jellyfin
from custom_components.voice_jellyfin.tv.remote import KEY_MAP
from custom_components.voice_jellyfin.const import (
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_SELECT, KEY_BACK, KEY_HOME,
    KEY_PLAY, KEY_PAUSE,
)

FIRE_TV_IP = "192.168.1.100"
FIRE_TV_PORT = 5555
FIRE_TV_TARGET = f"{FIRE_TV_IP}:{FIRE_TV_PORT}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(stdout: str = "", returncode: int = 0) -> MagicMock:
    """Return a mock asyncio subprocess whose communicate() yields stdout."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(
        return_value=(stdout.encode(), b"")
    )
    return proc


def _patch_adb(stdout: str = "", returncode: int = 0):
    """Patch asyncio.create_subprocess_exec to return a mock Fire TV process."""
    return patch(
        "asyncio.create_subprocess_exec",
        return_value=_make_proc(stdout, returncode),
    )


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class TestADBConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Fire TV responds 'connected to 192.168.1.100:5555'."""
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        with _patch_adb(f"connected to {FIRE_TV_TARGET}") as mock_exec:
            result = await ctrl.async_connect()

        assert result is True
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert "adb" in args
        assert f"connect" in args
        assert FIRE_TV_TARGET in args

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """Fire TV responds 'already connected' — still counts as success."""
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        with _patch_adb(f"already connected to {FIRE_TV_TARGET}"):
            result = await ctrl.async_connect()
        assert result is True

    @pytest.mark.asyncio
    async def test_connect_refused(self):
        """Device offline — adb returns error text, should return False."""
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        with _patch_adb("failed to connect to 192.168.1.100:5555", returncode=1):
            result = await ctrl.async_connect()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_adb_binary_missing(self):
        """adb not on PATH — FileNotFoundError handled gracefully."""
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("adb not found"),
        ):
            result = await ctrl.async_connect()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_timeout(self):
        """ADB hangs — asyncio.TimeoutError handled, returns False."""
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)

        async def _hang(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = None
            proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_hang):
            result = await ctrl.async_connect()
        assert result is False


# ---------------------------------------------------------------------------
# Key events (d-pad / remote simulation)
# ---------------------------------------------------------------------------

class TestKeyEvents:
    @pytest.mark.asyncio
    async def test_dpad_up(self):
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        with _patch_adb("") as mock_exec:
            await ctrl.async_key_event(KEY_MAP[KEY_UP])
        cmd = " ".join(mock_exec.call_args[0])
        assert "input keyevent" in cmd
        assert str(KEY_MAP[KEY_UP]) in cmd

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", [
        KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
        KEY_SELECT, KEY_BACK, KEY_HOME,
        KEY_PLAY, KEY_PAUSE,
    ])
    async def test_all_nav_keys_send_correct_keycode(self, key):
        """Every navigation key maps to a non-zero Android keycode."""
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        assert KEY_MAP[key] > 0
        with _patch_adb("") as mock_exec:
            await ctrl.async_key_event(KEY_MAP[key])
        cmd = " ".join(str(a) for a in mock_exec.call_args[0])
        assert str(KEY_MAP[key]) in cmd

    @pytest.mark.asyncio
    async def test_key_event_returns_on_error(self):
        """Non-zero returncode is tolerated — no exception raised."""
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        with _patch_adb("error: device offline", returncode=1):
            await ctrl.async_key_event(KEY_MAP[KEY_SELECT])  # should not raise


# ---------------------------------------------------------------------------
# App launching
# ---------------------------------------------------------------------------

class TestAppLaunch:
    JELLYFIN_PKG = "org.jellyfin.androidtv"

    @pytest.mark.asyncio
    async def test_start_activity_package_only(self):
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        with _patch_adb("") as mock_exec:
            await ctrl.async_start_activity(self.JELLYFIN_PKG)
        cmd = " ".join(str(a) for a in mock_exec.call_args[0])
        assert self.JELLYFIN_PKG in cmd
        assert "am start" in cmd

    @pytest.mark.asyncio
    async def test_start_activity_with_explicit_activity(self):
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        activity = f"{self.JELLYFIN_PKG}/.MainActivity"
        with _patch_adb("") as mock_exec:
            await ctrl.async_start_activity(self.JELLYFIN_PKG, activity)
        cmd = " ".join(str(a) for a in mock_exec.call_args[0])
        assert f"{self.JELLYFIN_PKG}/{activity}" in cmd or activity in cmd

    @pytest.mark.asyncio
    async def test_deep_link_launch_jellyfin_no_item(self):
        """async_launch_jellyfin with no item_id opens the Jellyfin home screen."""
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        with _patch_adb("") as mock_exec:
            await async_launch_jellyfin(ctrl)
        cmd = " ".join(str(a) for a in mock_exec.call_args[0])
        assert self.JELLYFIN_PKG in cmd

    @pytest.mark.asyncio
    async def test_deep_link_launch_jellyfin_with_item(self):
        """async_launch_jellyfin with an item_id sends a deep link URI."""
        ctrl = ADBController(FIRE_TV_IP, FIRE_TV_PORT)
        item_id = "abc-123-xyz"
        with _patch_adb("") as mock_exec:
            await async_launch_jellyfin(ctrl, item_id=item_id)
        cmd = " ".join(str(a) for a in mock_exec.call_args[0])
        assert item_id in cmd


# ---------------------------------------------------------------------------
# AndroidTVController (higher-level wrapper)
# ---------------------------------------------------------------------------

class TestAndroidTVController:
    @pytest.mark.asyncio
    async def test_send_key_via_ha_service_preferred(self):
        """AndroidTVController calls HA androidtv service first, not raw ADB."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.has_service = MagicMock(return_value=True)
        hass.services.async_call = AsyncMock()

        ctrl = AndroidTVController(hass, "media_player.fire_tv")
        await ctrl.async_send_key(KEY_UP)

        hass.services.async_call.assert_awaited_once()
        call_args = hass.services.async_call.call_args
        # should have called androidtv or remote domain
        assert call_args[0][0] in ("androidtv", "remote", "media_player")

    @pytest.mark.asyncio
    async def test_send_key_falls_back_to_media_player(self):
        """When androidtv service unavailable, falls back to media_player.play_media."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.has_service = MagicMock(return_value=False)
        hass.services.async_call = AsyncMock()

        ctrl = AndroidTVController(hass, "media_player.fire_tv")
        await ctrl.async_send_key(KEY_DOWN)

        hass.services.async_call.assert_awaited_once()
        domain, service = hass.services.async_call.call_args[0][:2]
        assert domain == "media_player"
        assert service == "play_media"

    @pytest.mark.asyncio
    async def test_wake_device(self):
        """When androidtv service unavailable, wake falls back to media_player.turn_on."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.has_service = MagicMock(return_value=False)
        hass.services.async_call = AsyncMock()

        ctrl = AndroidTVController(hass, "media_player.fire_tv")
        await ctrl.async_wake()

        hass.services.async_call.assert_awaited_once()
        domain, service = hass.services.async_call.call_args[0][:2]
        assert domain == "media_player"
        assert service == "turn_on"

    @pytest.mark.asyncio
    async def test_repeat_key_sends_multiple_events(self):
        """send_key with repeat=3 calls the HA service 3 times."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.has_service = MagicMock(return_value=False)
        hass.services.async_call = AsyncMock()

        ctrl = AndroidTVController(hass, "media_player.fire_tv")
        await ctrl.async_send_key(KEY_DOWN, repeat=3)
        assert hass.services.async_call.await_count == 3
