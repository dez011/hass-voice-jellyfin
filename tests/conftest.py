"""Shared pytest fixtures for voice_jellyfin tests."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Constants mirrored here to avoid circular imports in test discovery
# ---------------------------------------------------------------------------

DOMAIN = "voice_jellyfin"

SAMPLE_CONFIG: dict[str, Any] = {
    "network_mode": "local",
    "jellyfin_url": "http://localhost:8096",
    "jellyfin_api_key": "test-api-key-abc123",
    "jellyfin_default_user": "user-id-xyz",
    "android_tv_entity": "media_player.living_room_tv",
    "adb_host": "192.168.1.100",
    "adb_port": 5555,
    "tv_wake_support": True,
    "ai_provider": "ollama",
    "ollama_host": "localhost",
    "ollama_port": 11434,
    "ollama_https": False,
    "ollama_model": "llama3",
    "ollama_context_size": 4096,
    "ollama_keep_alive": "5m",
    "ai_streaming": False,
    "ai_timeout": 15,
    "nav_wake_phrase": "navigation mode",
    "nav_timeout": "60",
    "nav_continuous": True,
    "nav_confirmation_speech": True,
    "button_entity": "input_button.accessibility_btn",
    "button_trigger": "state_changed",
}


@pytest.fixture
def mock_hass():
    """Return a minimal mock HomeAssistant object."""
    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=lambda: None)
    hass.bus.async_fire = MagicMock()
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_call = AsyncMock(return_value=None)
    hass.services.async_register = MagicMock()
    hass.async_create_task = MagicMock(side_effect=lambda coro: coro)
    hass.config_entries = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Return a mock ConfigEntry populated with SAMPLE_CONFIG."""
    entry = MagicMock()
    entry.entry_id = "test-entry-id-001"
    entry.data = SAMPLE_CONFIG.copy()
    entry.options = {}
    entry.add_update_listener = MagicMock(return_value=lambda: None)
    return entry


@pytest.fixture
def mock_jellyfin_client():
    """Return a mock JellyfinClient with sensible defaults."""
    from custom_components.voice_jellyfin.jellyfin.models import (
        Library,
        MediaItem,
        PlaybackSession,
    )

    client = MagicMock()
    client.async_connect = AsyncMock(return_value={"Version": "10.9.0"})
    client.async_close = AsyncMock()
    client.async_get_libraries = AsyncMock(
        return_value=[
            Library(id="lib-001", name="Movies", type="movies"),
            Library(id="lib-002", name="TV Shows", type="tvshows"),
        ]
    )
    client.async_search = AsyncMock(
        return_value=[
            MediaItem(id="item-001", name="The Dark Knight", type="Movie", year=2008),
            MediaItem(id="item-002", name="Batman Begins", type="Movie", year=2005),
        ]
    )
    client.async_get_recently_added = AsyncMock(
        return_value=[
            MediaItem(id="item-003", name="Oppenheimer", type="Movie", year=2023),
        ]
    )
    client.async_get_resume_items = AsyncMock(
        return_value=[
            MediaItem(id="item-004", name="Breaking Bad S01E01", type="Episode"),
        ]
    )
    client.async_get_favorites = AsyncMock(return_value=[])
    client.async_get_by_genre = AsyncMock(return_value=[])
    client.async_get_sessions = AsyncMock(
        return_value=[
            PlaybackSession(
                id="sess-001",
                user_id="user-id-xyz",
                item=MediaItem(id="item-004", name="Breaking Bad S01E01", type="Episode"),
                position_ticks=10_000_000,
                is_paused=False,
            )
        ]
    )
    client.async_play = AsyncMock()
    client.async_pause = AsyncMock()
    client.async_stop = AsyncMock()
    client.async_resume = AsyncMock(return_value="Breaking Bad S01E01")
    client._auth = MagicMock()
    client._auth.user_id = "user-id-xyz"
    return client


@pytest.fixture
def mock_ai_provider():
    """Return a mock AIProvider that responds with a PLAY JSON intent."""
    import json
    from custom_components.voice_jellyfin.ai.base import AIProvider

    class _MockProvider(AIProvider):
        @property
        def name(self) -> str:
            return "MockProvider"

        async def async_query(self, messages, system_prompt):
            return json.dumps({
                "intent": "PLAY",
                "params": {"query": "The Dark Knight"},
                "speech": "Playing The Dark Knight.",
            })

    return _MockProvider()
