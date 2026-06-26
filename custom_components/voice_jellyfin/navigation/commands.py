"""Spoken-phrase to key-constant mappings for Navigation Mode."""
from __future__ import annotations

from ..const import (
    KEY_UP,
    KEY_DOWN,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_SELECT,
    KEY_BACK,
    KEY_HOME,
    KEY_PLAY,
    KEY_PAUSE,
    KEY_STOP,
    KEY_FAST_FORWARD,
    KEY_REWIND,
    KEY_PAGE_UP,
    KEY_PAGE_DOWN,
    KEY_VOLUME_UP,
    KEY_VOLUME_DOWN,
    KEY_MUTE,
)

# Map of lowercased spoken phrases → KEY_* constant
VOICE_TO_KEY: dict[str, str] = {
    # Directional
    "up": KEY_UP,
    "move up": KEY_UP,
    "go up": KEY_UP,
    "scroll up": KEY_UP,
    "down": KEY_DOWN,
    "move down": KEY_DOWN,
    "go down": KEY_DOWN,
    "scroll down": KEY_DOWN,
    "left": KEY_LEFT,
    "move left": KEY_LEFT,
    "go left": KEY_LEFT,
    "right": KEY_RIGHT,
    "move right": KEY_RIGHT,
    "go right": KEY_RIGHT,
    # Confirm / select
    "select": KEY_SELECT,
    "ok": KEY_SELECT,
    "okay": KEY_SELECT,
    "enter": KEY_SELECT,
    "confirm": KEY_SELECT,
    "click": KEY_SELECT,
    "press": KEY_SELECT,
    # Navigation
    "back": KEY_BACK,
    "go back": KEY_BACK,
    "return": KEY_BACK,
    "previous": KEY_BACK,
    "home": KEY_HOME,
    "go home": KEY_HOME,
    "main menu": KEY_HOME,
    # Playback
    "play": KEY_PLAY,
    "start": KEY_PLAY,
    "pause": KEY_PAUSE,
    "stop": KEY_STOP,
    "fast forward": KEY_FAST_FORWARD,
    "forward": KEY_FAST_FORWARD,
    "skip forward": KEY_FAST_FORWARD,
    "rewind": KEY_REWIND,
    "skip back": KEY_REWIND,
    "go back a bit": KEY_REWIND,
    # Paging
    "page up": KEY_PAGE_UP,
    "page down": KEY_PAGE_DOWN,
    "next page": KEY_PAGE_DOWN,
    "previous page": KEY_PAGE_UP,
    # Volume
    "volume up": KEY_VOLUME_UP,
    "louder": KEY_VOLUME_UP,
    "volume down": KEY_VOLUME_DOWN,
    "quieter": KEY_VOLUME_DOWN,
    "softer": KEY_VOLUME_DOWN,
    "mute": KEY_MUTE,
    "silence": KEY_MUTE,
    "unmute": KEY_MUTE,
}

# Patterns that signal the user wants to repeat the previous key action
REPEAT_PATTERNS: list[str] = [
    "again",
    "one more",
    "more",
    "keep going",
    "continue",
    "repeat",
    "do it again",
    "one more time",
]

# Patterns that signal the user went too far and wants to reverse
REVERSE_PATTERNS: list[str] = [
    "too far",
    "too much",
    "go back one",
    "back one",
    "undo",
    "too many",
    "overshoot",
]
