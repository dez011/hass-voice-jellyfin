"""Select platform — AI Provider switcher."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, AI_PROVIDERS, AI_PROVIDER_LABELS
from .coordinator import VoiceJellyfinCoordinator
from .entity import VoiceJellyfinEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VoiceJellyfinCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AIProviderSelect(coordinator)])


class AIProviderSelect(VoiceJellyfinEntity, SelectEntity):
    _attr_name = "AI Provider"
    _attr_icon = "mdi:robot"
    _attr_options = [AI_PROVIDER_LABELS[p] for p in AI_PROVIDERS]

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "ai_provider_select")

    @property
    def current_option(self) -> str | None:
        return (self.coordinator.data or {}).get("current_provider")

    async def async_select_option(self, option: str) -> None:
        # Find key by label
        key = next((k for k, v in AI_PROVIDER_LABELS.items() if v == option), None)
        if key:
            self.coordinator._current_provider_label = option
            await self.coordinator._async_load_ai_provider(
                {**self.coordinator.entry.data, "ai_provider": key}
            )
            self.async_write_ha_state()
