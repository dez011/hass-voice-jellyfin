"""Serve and auto-load the Voice Jellyfin Lovelace card.

Without this the card ships inside the integration but is unreachable from
the browser: the user has to hand-copy voice-jellyfin-card.js into
config/www/ and register it under Settings -> Dashboards -> Resources
before `type: custom:voice-jellyfin-card` resolves. Registering the static
path here and adding the URL to the frontend's extra JS makes the card
available as soon as the integration loads.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import LOGGER_NAME, VERSION

_LOGGER = logging.getLogger(LOGGER_NAME)

CARD_FILENAME = "voice-jellyfin-card.js"
# Cache-busted on VERSION so a card update is picked up instead of the
# browser serving a stale copy after an upgrade.
CARD_URL = f"/voice_jellyfin/{CARD_FILENAME}?v={VERSION}"
_STATIC_URL = f"/voice_jellyfin/{CARD_FILENAME}"

_REGISTERED_KEY = "voice_jellyfin_frontend_registered"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the card and ask the frontend to load it.

    Best-effort: a failure here costs the dashboard card, not the
    integration, so every step degrades to a warning rather than raising
    and taking config entry setup down with it.
    """
    if hass.data.get(_REGISTERED_KEY):
        return

    card_path = Path(__file__).parent / "lovelace" / CARD_FILENAME
    if not card_path.is_file():
        _LOGGER.warning("Lovelace card not found at %s — card unavailable", card_path)
        return

    try:
        await _async_register_static_path(hass, _STATIC_URL, str(card_path))
    except Exception as exc:  # pragma: no cover - defensive
        _LOGGER.warning("Could not serve the Lovelace card: %s", exc)
        return

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, CARD_URL)
    except Exception as exc:  # pragma: no cover - defensive
        _LOGGER.warning(
            "Card is served at %s but could not be auto-loaded (%s). "
            "Add it manually under Settings -> Dashboards -> Resources.",
            _STATIC_URL,
            exc,
        )

    hass.data[_REGISTERED_KEY] = True
    _LOGGER.debug("Lovelace card registered at %s", CARD_URL)


async def _async_register_static_path(
    hass: HomeAssistant, url: str, path: str
) -> None:
    """Register a static file path across HA versions.

    async_register_static_paths landed in 2024.7; older cores only have the
    blocking register_static_path, which newer cores warn about.
    """
    http = hass.http
    register_async = getattr(http, "async_register_static_paths", None)
    if register_async is not None:
        from homeassistant.components.http import StaticPathConfig

        await register_async([StaticPathConfig(url, path, False)])
        return

    http.register_static_path(url, path, False)
