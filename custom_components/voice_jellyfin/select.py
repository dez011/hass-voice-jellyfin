"""Select platform — AI Provider and Control Method switchers."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    AI_PROVIDERS,
    AI_PROVIDER_LABELS,
    CONF_CONTROL_METHOD,
    CONTROL_METHODS,
    CONTROL_METHOD_LABELS,
    DEFAULT_CONTROL_METHOD,
)
from .coordinator import VoiceJellyfinCoordinator
from .entity import VoiceJellyfinEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VoiceJellyfinCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        AIProviderSelect(coordinator),
        ControlMethodSelect(coordinator),
    ])


class AIProviderSelect(VoiceJellyfinEntity, SelectEntity):
    _attr_name = "AI Provider"
    _attr_icon = "mdi:robot"
    _attr_options = [AI_PROVIDER_LABELS[p] for p in AI_PROVIDERS]

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "ai_provider_select")

    @property
    def current_option(self) -> str | None:
        # Coordinator stores the provider KEY; entity options are labels
        key = (self.coordinator.data or {}).get("current_provider")
        if not key:
            return None
        return AI_PROVIDER_LABELS.get(key, key)

    async def async_select_option(self, option: str) -> None:
        # Find key by label
        key = next((k for k, v in AI_PROVIDER_LABELS.items() if v == option), None)
        if key:
            self.coordinator._current_provider_label = key
            entry = self.coordinator.entry
            merged = {**entry.data, **(entry.options or {}), "ai_provider": key}
            await self.coordinator._async_load_ai_provider(merged)
            data = dict(self.coordinator.data or {})
            data["current_provider"] = key
            self.coordinator.async_set_updated_data(data)
            self.async_write_ha_state()


class ControlMethodSelect(VoiceJellyfinEntity, SelectEntity):
    """Chooses how playback/navigation commands are delivered.

    Switchable at runtime so both transports can be compared against a live
    device without a reconfigure and restart between attempts. The choice is
    also persisted to the config entry so it survives a restart.
    """

    _attr_name = "Control Method"
    _attr_icon = "mdi:remote"
    _attr_options = [CONTROL_METHOD_LABELS[m] for m in CONTROL_METHODS]

    def __init__(self, coordinator: VoiceJellyfinCoordinator) -> None:
        super().__init__(coordinator, "control_method_select")

    @property
    def current_option(self) -> str | None:
        key = getattr(self.coordinator, "control_method", DEFAULT_CONTROL_METHOD)
        return CONTROL_METHOD_LABELS.get(key, key)

    async def async_select_option(self, option: str) -> None:
        key = next(
            (k for k, v in CONTROL_METHOD_LABELS.items() if v == option), None
        )
        if key is None:
            return
        self.coordinator.control_method = key

        # Persist so the choice isn't lost on restart.
        entry = self.coordinator.entry
        self.hass.config_entries.async_update_entry(
            entry, options={**(entry.options or {}), CONF_CONTROL_METHOD: key}
        )

        data = dict(self.coordinator.data or {})
        data["control_method"] = key
        self.coordinator.async_set_updated_data(data)
        self.async_write_ha_state()
