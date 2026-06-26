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
