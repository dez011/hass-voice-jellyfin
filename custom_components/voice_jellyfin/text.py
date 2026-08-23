"""Text platform — type any command or search query and fire it."""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
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
    async_add_entities([VoiceJellyfinCommandInput(coordinator)])


class VoiceJellyfinCommandInput(VoiceJellyfinEntity, TextEntity):
    _attr_name = "Command"
    _attr_icon = "mdi:console"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 1
    _attr_native_max = 255

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "command_input")
        self._value = ""

    @property
    def native_value(self) -> str:
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()
        await self.coordinator.async_send_command(value)
