"""Shared logic for picking which Jellyfin session a command should target.

With more than one person/device on the same Jellyfin server, "grab whatever
session the API returns first" is ambiguous — a command meant for one TV can
land on another. Every command handler goes through pick_session()/
pick_now_playing() here instead of hand-rolling session selection, so the
device-targeting behavior (and its tests) live in exactly one place.
"""
from __future__ import annotations

from typing import Optional

from .models import PlaybackSession


def pick_session(
    sessions: list[PlaybackSession],
    device_filter: Optional[str] = None,
    require_item: bool = True,
    paused: Optional[bool] = None,
    user_id: Optional[str] = None,
) -> Optional[PlaybackSession]:
    """Return the best session to target, or None.

    :param sessions: All sessions from /Sessions.
    :param device_filter: Case-insensitive substring matched against each
        session's DeviceName or Client app name (e.g. "Living Room",
        "Astra"). When set, ONLY matching sessions are considered — there is
        no silent fallback to an unrelated session, since that would defeat
        the point of targeting a specific TV. When unset/blank, any session
        is eligible (the old single-TV behavior).
    :param require_item: Only consider sessions with an active NowPlayingItem.
    :param paused: None = don't care, True = only paused sessions,
        False = only actively-playing sessions.
    :param user_id: Jellyfin user id (PlaybackSession.user_id) to restrict to.
        Without this, commands land on whichever session the API lists
        first — fine for a single-user household, ambiguous once more than
        one person has a session open. Combines with device_filter (both
        must match when both are set).
    """
    candidates = [s for s in sessions if (not require_item or s.item)]
    if paused is True:
        candidates = [s for s in candidates if s.is_paused]
    elif paused is False:
        candidates = [s for s in candidates if not s.is_paused]

    if user_id:
        candidates = [s for s in candidates if s.user_id == user_id]

    needle = (device_filter or "").strip().lower()
    if needle:
        candidates = [
            s for s in candidates
            if needle in (s.device_name or "").lower()
            or needle in (s.client or "").lower()
        ]

    return candidates[0] if candidates else None


def pick_now_playing(
    sessions: list[PlaybackSession],
    device_filter: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[PlaybackSession]:
    """Prefer an actively-playing session; fall back to a paused one.

    Used for "what's playing" style queries where a paused session is still
    a reasonable answer if nothing is actively playing.
    """
    return (
        pick_session(sessions, device_filter, require_item=True, paused=False, user_id=user_id)
        or pick_session(sessions, device_filter, require_item=True, paused=None, user_id=user_id)
    )
