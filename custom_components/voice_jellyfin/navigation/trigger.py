"""Physical button trigger — watches an HA entity to activate Navigation Mode."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.const import EVENT_STATE_CHANGED

if TYPE_CHECKING:
    from ..coordinator import VoiceJellyfinCoordinator

_LOGGER = logging.getLogger(__name__)

# States / attributes that indicate a "press" event
_TRIGGER_STATES = {"on", "press", "pressed", "true", "1"}


class ButtonTrigger:
    """Monitors an entity and activates Navigation Mode when triggered."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str,
        coordinator: "VoiceJellyfinCoordinator",
    ) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._coordinator = coordinator
        self._unsub: Optional[Callable[[], None]] = None

    async def async_attach(self) -> None:
        """Start listening for state changes on the configured entity."""
        self._unsub = self._hass.bus.async_listen(
            EVENT_STATE_CHANGED,
            self._on_state_change,
        )
        _LOGGER.debug(
            "ButtonTrigger attached to entity: %s", self._entity_id
        )

    def async_detach(self) -> None:
        """Stop listening."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _on_state_change(self, event: Event) -> None:
        """Handle state-changed events."""
        if event.data.get("entity_id") != self._entity_id:
            return

        new_state = event.data.get("new_state")
        if new_state is None:
            return

        state_str = str(new_state.state).lower()
        if state_str in _TRIGGER_STATES:
            _LOGGER.debug(
                "ButtonTrigger fired (entity=%s state=%s)",
                self._entity_id,
                state_str,
            )
            nav = self._coordinator.navigation_mode
            if nav:
                self._hass.async_create_task(nav.async_activate())
