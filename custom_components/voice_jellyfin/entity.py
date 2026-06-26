"""Base entity for Voice Jellyfin."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VoiceJellyfinCoordinator


class VoiceJellyfinEntity(CoordinatorEntity[VoiceJellyfinCoordinator]):
    """Base class for all Voice Jellyfin entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VoiceJellyfinCoordinator, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{unique_suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": "Voice Jellyfin",
            "manufacturer": "voice_jellyfin",
            "model": "HACS Integration",
            "sw_version": coordinator.entry.data.get("version", "0.1.0"),
        }
