"""Sensor platform for Voice Jellyfin."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VoiceJellyfinCoordinator
from .entity import VoiceJellyfinEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VoiceJellyfinCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        VoiceJellyfinStatusSensor(coordinator),
        VoiceJellyfinProviderSensor(coordinator),
        VoiceJellyfinDeviceSensor(coordinator),
        VoiceJellyfinLastCommandSensor(coordinator),
        VoiceJellyfinLastMediaSensor(coordinator),
        VoiceJellyfinNowPlayingSensor(coordinator),
        VoiceJellyfinActiveUserSensor(coordinator),
        VoiceJellyfinActiveSessionSensor(coordinator),
        VoiceJellyfinSessionsSensor(coordinator),
    ])


class VoiceJellyfinStatusSensor(VoiceJellyfinEntity, SensorEntity):
    _attr_name = "Status"
    _attr_icon = "mdi:microphone"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        if data.get("navigation_active"):
            return "Navigating"
        return "Connected" if data.get("connected") else "Disconnected"


class VoiceJellyfinProviderSensor(VoiceJellyfinEntity, SensorEntity):
    _attr_name = "AI Provider"
    _attr_icon = "mdi:brain"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "current_provider")

    @property
    def native_value(self) -> str:
        return (self.coordinator.data or {}).get("current_provider", "None")


class VoiceJellyfinDeviceSensor(VoiceJellyfinEntity, SensorEntity):
    _attr_name = "Current Device"
    _attr_icon = "mdi:television-play"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "current_device")

    @property
    def native_value(self) -> str:
        return (self.coordinator.data or {}).get("current_device", "None")


class VoiceJellyfinLastCommandSensor(VoiceJellyfinEntity, SensorEntity):
    _attr_name = "Last Command"
    _attr_icon = "mdi:console"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "last_command")

    @property
    def native_value(self) -> str:
        return (self.coordinator.data or {}).get("last_command", "")


class VoiceJellyfinLastMediaSensor(VoiceJellyfinEntity, SensorEntity):
    _attr_name = "Last Media"
    _attr_icon = "mdi:movie-open"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "last_media")

    @property
    def native_value(self) -> str:
        return (self.coordinator.data or {}).get("last_media", "")


class VoiceJellyfinNowPlayingSensor(VoiceJellyfinEntity, SensorEntity):
    """What's actually playing in Jellyfin right now — which client app,
    which device, and which user — the visibility that was missing when
    more than one person/TV shares the same server."""

    _attr_name = "Now Playing"
    _attr_icon = "mdi:play-circle"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "now_playing")

    @property
    def native_value(self) -> str:
        now = (self.coordinator.data or {}).get("now_playing")
        if not now or not now.get("title"):
            return "Nothing playing"
        return now["title"]

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        now = (self.coordinator.data or {}).get("now_playing") or {}
        return {
            "client": now.get("client") or "Unknown",
            "device": now.get("device") or "Unknown",
            "user": now.get("user") or "Unknown",
            "paused": now.get("paused", False),
        }


class VoiceJellyfinActiveUserSensor(VoiceJellyfinEntity, SensorEntity):
    """The Jellyfin username this entry is configured to control."""

    _attr_name = "Active User"
    _attr_icon = "mdi:account"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "active_user")

    @property
    def native_value(self) -> str:
        return (self.coordinator.data or {}).get("active_user") or "Not configured"


class VoiceJellyfinActiveSessionSensor(VoiceJellyfinEntity, SensorEntity):
    """The session that will be targeted by the next command."""

    _attr_name = "Active Session"
    _attr_icon = "mdi:television-account"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "active_session")

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        session = data.get("active_session")
        if not session:
            return "No session"
        controllable = data.get("remote_controllable", False)
        return f"{session} {'✓' if controllable else '⚠ no remote control'}"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data or {}
        return {
            "remote_controllable": data.get("remote_controllable", False),
            "remote_control_note": (
                "Client supports remote control — buttons will work"
                if data.get("remote_controllable")
                else "Client does NOT support remote control (e.g. Plezy). "
                     "Use the official Jellyfin app or Infuse."
            ),
        }


class VoiceJellyfinSessionsSensor(VoiceJellyfinEntity, SensorEntity):
    """All real user sessions and their remote control status."""

    _attr_name = "Sessions"
    _attr_icon = "mdi:account-multiple"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "sessions")

    @property
    def native_value(self) -> str:
        sessions = (self.coordinator.data or {}).get("real_sessions", [])
        return f"{len(sessions)} session(s)"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        sessions = (self.coordinator.data or {}).get("real_sessions", [])
        return {"sessions": sessions}
