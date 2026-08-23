"""Button platform — one-press media controls on the HA dashboard."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VoiceJellyfinCoordinator
from .entity import VoiceJellyfinEntity

_BUTTONS = [
    ("Pause",            "pause",            "mdi:pause"),
    ("Resume",           "resume",           "mdi:play"),
    ("Stop",             "stop",             "mdi:stop"),
    ("Next Episode",     "next episode",     "mdi:skip-next"),
    ("Previous Episode", "previous episode", "mdi:skip-previous"),
    ("Back",             "back",             "mdi:arrow-left"),
    ("Open Jellyfin",    "open jellyfin",    "mdi:jellyfish"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VoiceJellyfinCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        VoiceJellyfinButton(coordinator, name, cmd, icon)
        for name, cmd, icon in _BUTTONS
    ])


class VoiceJellyfinButton(VoiceJellyfinEntity, ButtonEntity):
    def __init__(
        self,
        coordinator: VoiceJellyfinCoordinator,
        name: str,
        command: str,
        icon: str,
    ) -> None:
        suffix = name.lower().replace(" ", "_")
        super().__init__(coordinator, f"btn_{suffix}")
        self._attr_name = name
        self._attr_icon = icon
        self._command = command

    async def async_press(self) -> None:
        await self.coordinator.async_send_command(self._command)
