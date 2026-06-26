"""Switch platform — Navigation Mode on/off."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    async_add_entities([NavigationModeSwitch(coordinator)])


class NavigationModeSwitch(VoiceJellyfinEntity, SwitchEntity):
    _attr_name = "Navigation Mode"
    _attr_icon = "mdi:gamepad-variant"

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "navigation_mode")

    @property
    def is_on(self) -> bool:
        return (self.coordinator.data or {}).get("navigation_active", False)

    async def async_turn_on(self, **kwargs: object) -> None:
        if self.coordinator.navigation_mode:
            await self.coordinator.navigation_mode.async_activate()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        if self.coordinator.navigation_mode:
            await self.coordinator.navigation_mode.async_deactivate()
        self.async_write_ha_state()
