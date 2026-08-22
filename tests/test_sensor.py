"""Tests for the Voice Jellyfin sensor platform, focused on Now Playing —
the sensor that finally shows which client/device/user is actually active,
which was previously invisible from the HA UI."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.voice_jellyfin.sensor import VoiceJellyfinNowPlayingSensor


def _coordinator_with_data(data):
    coord = MagicMock()
    coord.data = data
    return coord


def test_now_playing_shows_title():
    coord = _coordinator_with_data({
        "now_playing": {"title": "The Matrix", "client": "Astra", "device": "Bedroom", "user": "Brother", "paused": False}
    })
    sensor = VoiceJellyfinNowPlayingSensor(coord)
    assert sensor.native_value == "The Matrix"
    assert sensor.extra_state_attributes == {
        "client": "Astra", "device": "Bedroom", "user": "Brother", "paused": False,
    }


def test_now_playing_nothing_playing():
    coord = _coordinator_with_data({"now_playing": None})
    sensor = VoiceJellyfinNowPlayingSensor(coord)
    assert sensor.native_value == "Nothing playing"
    assert sensor.extra_state_attributes["client"] == "Unknown"


def test_now_playing_handles_missing_data():
    coord = _coordinator_with_data(None)
    sensor = VoiceJellyfinNowPlayingSensor(coord)
    assert sensor.native_value == "Nothing playing"


def test_now_playing_missing_optional_fields_default_unknown():
    coord = _coordinator_with_data({"now_playing": {"title": "Show"}})
    sensor = VoiceJellyfinNowPlayingSensor(coord)
    assert sensor.native_value == "Show"
    attrs = sensor.extra_state_attributes
    assert attrs["client"] == "Unknown"
    assert attrs["device"] == "Unknown"
    assert attrs["user"] == "Unknown"
    assert attrs["paused"] is False
