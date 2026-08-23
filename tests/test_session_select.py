"""Tests for jellyfin/session_select.py — the device-targeting logic that
lets more than one person/TV share a Jellyfin server without commands
crossing over."""
from __future__ import annotations

from custom_components.voice_jellyfin.jellyfin.models import MediaItem, PlaybackSession
from custom_components.voice_jellyfin.jellyfin.session_select import (
    pick_now_playing,
    pick_session,
)


def _session(id_, device_name="", client="", paused=False, item=True):
    return PlaybackSession(
        id=id_,
        user_id="u1",
        item=MediaItem(id=f"item-{id_}", name="Something", type="Movie") if item else None,
        is_paused=paused,
        device_name=device_name,
        client=client,
    )


def test_no_filter_returns_first_candidate():
    sessions = [_session("a"), _session("b")]
    assert pick_session(sessions).id == "a"


def test_device_filter_matches_by_device_name():
    sessions = [
        _session("living-room", device_name="Living Room Fire TV"),
        _session("bedroom", device_name="Bedroom Fire TV"),
    ]
    assert pick_session(sessions, device_filter="bedroom").id == "bedroom"


def test_device_filter_matches_by_client_name():
    sessions = [
        _session("a", client="Jellyfin Android TV"),
        _session("b", client="Astra"),
    ]
    assert pick_session(sessions, device_filter="astra").id == "b"


def test_device_filter_is_case_insensitive():
    sessions = [_session("a", device_name="Living Room")]
    assert pick_session(sessions, device_filter="LIVING room").id == "a"


def test_device_filter_no_match_but_device_exists_returns_none():
    """Configured device IS present in sessions but has nothing playing/paused
    on it — don't grab a different device's session."""
    sessions = [
        _session("brothers-tv", device_name="Brother's Fire TV"),
        _session("my-tv", device_name="My Living Room Fire TV", item=False),
    ]
    # My TV exists but has no item; brothers-tv has item but wrong device
    assert pick_session(sessions, device_filter="my living room") is None


def test_device_filter_no_match_device_absent_falls_back():
    """Configured device has ZERO sessions (e.g. TV is off, user is on iPad).
    Fall back to any available real session so commands still work."""
    sessions = [_session("ipad", device_name="iPad", client="Plezy")]
    # "fire tv" has no sessions at all → fall back to iPad
    result = pick_session(sessions, device_filter="fire tv")
    assert result is not None
    assert result.id == "ipad"


def test_device_filter_blank_string_behaves_as_unfiltered():
    sessions = [_session("a"), _session("b")]
    assert pick_session(sessions, device_filter="   ").id == "a"


def test_require_item_excludes_idle_sessions():
    sessions = [_session("idle", item=False), _session("playing", item=True)]
    assert pick_session(sessions, require_item=True).id == "playing"


def test_require_item_false_allows_idle_sessions():
    sessions = [_session("idle", item=False)]
    assert pick_session(sessions, require_item=False).id == "idle"


def test_paused_true_filters_to_paused_only():
    sessions = [_session("playing", paused=False), _session("paused", paused=True)]
    assert pick_session(sessions, paused=True).id == "paused"


def test_paused_false_filters_to_playing_only():
    sessions = [_session("playing", paused=False), _session("paused", paused=True)]
    assert pick_session(sessions, paused=False).id == "playing"


def test_empty_sessions_returns_none():
    assert pick_session([]) is None


def test_two_tv_isolation():
    """The exact scenario this feature exists for: two people, two TVs, one
    Jellyfin server. Each target must only ever see its own session."""
    sessions = [
        _session("mine", device_name="Living Room Fire TV", client="Jellyfin Android TV"),
        _session("brothers", device_name="Bedroom Fire TV", client="Astra"),
    ]
    assert pick_session(sessions, device_filter="Living Room").id == "mine"
    assert pick_session(sessions, device_filter="Bedroom").id == "brothers"
    assert pick_session(sessions, device_filter="Astra").id == "brothers"


# ---------------------------------------------------------------------------
# pick_now_playing — prefer actively playing, fall back to paused
# ---------------------------------------------------------------------------

def test_now_playing_prefers_unpaused():
    sessions = [_session("paused", paused=True), _session("playing", paused=False)]
    assert pick_now_playing(sessions).id == "playing"


def test_now_playing_falls_back_to_paused_when_nothing_active():
    sessions = [_session("paused", paused=True)]
    assert pick_now_playing(sessions).id == "paused"


def test_now_playing_respects_device_filter_in_both_tiers():
    """When the configured device exists and has a paused session, prefer it
    over an actively-playing session on a different device."""
    sessions = [
        _session("other-playing", device_name="Other TV", paused=False),
        _session("mine-paused", device_name="My TV", paused=True),
    ]
    result = pick_now_playing(sessions, device_filter="My TV")
    assert result.id == "mine-paused"


def test_now_playing_falls_back_when_configured_device_absent():
    """If the configured device has no sessions at all, fall back to whatever
    is playing — user switched to a different device (phone, iPad, etc.)."""
    sessions = [_session("ipad", device_name="iPad", client="Plezy", paused=True)]
    result = pick_now_playing(sessions, device_filter="Fire TV")
    assert result is not None
    assert result.id == "ipad"


def test_now_playing_no_sessions_returns_none():
    assert pick_now_playing([]) is None
