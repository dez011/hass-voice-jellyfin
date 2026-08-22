"""Tests for Lovelace card registration.

The card ships inside the integration but is useless unless it is both
served over HTTP and registered with the frontend — without that the user
sees no card at all and has no obvious reason why.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_hass(with_async_static: bool = True) -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.http = MagicMock()
    if with_async_static:
        hass.http.async_register_static_paths = AsyncMock()
        del hass.http.register_static_path
    else:
        # Older cores expose only the blocking variant.
        del hass.http.async_register_static_paths
        hass.http.register_static_path = MagicMock()
    return hass


@pytest.mark.asyncio
async def test_registers_static_path_and_extra_js():
    from custom_components.voice_jellyfin.frontend import (
        CARD_URL,
        async_register_frontend,
    )

    hass = _make_hass()
    with patch(
        "homeassistant.components.frontend.add_extra_js_url"
    ) as add_js:
        await async_register_frontend(hass)

    hass.http.async_register_static_paths.assert_awaited_once()
    add_js.assert_called_once_with(hass, CARD_URL)


@pytest.mark.asyncio
async def test_card_url_is_cache_busted_on_version():
    """A bare URL means browsers keep serving the pre-upgrade card."""
    from custom_components.voice_jellyfin.frontend import CARD_URL
    from custom_components.voice_jellyfin.const import VERSION

    assert CARD_URL.endswith(f"?v={VERSION}")


@pytest.mark.asyncio
async def test_registration_is_idempotent():
    """Every config entry calls this; the card must register once."""
    from custom_components.voice_jellyfin.frontend import async_register_frontend

    hass = _make_hass()
    with patch("homeassistant.components.frontend.add_extra_js_url") as add_js:
        await async_register_frontend(hass)
        await async_register_frontend(hass)
        await async_register_frontend(hass)

    assert hass.http.async_register_static_paths.await_count == 1
    assert add_js.call_count == 1


@pytest.mark.asyncio
async def test_falls_back_to_blocking_register_on_older_cores():
    from custom_components.voice_jellyfin.frontend import async_register_frontend

    hass = _make_hass(with_async_static=False)
    with patch("homeassistant.components.frontend.add_extra_js_url"):
        await async_register_frontend(hass)

    hass.http.register_static_path.assert_called_once()


@pytest.mark.asyncio
async def test_static_path_failure_does_not_raise():
    """A frontend problem must not take down config entry setup."""
    from custom_components.voice_jellyfin.frontend import async_register_frontend

    hass = _make_hass()
    hass.http.async_register_static_paths = AsyncMock(
        side_effect=RuntimeError("http not ready")
    )

    await async_register_frontend(hass)  # must not raise

    assert "voice_jellyfin_frontend_registered" not in hass.data


@pytest.mark.asyncio
async def test_extra_js_failure_still_serves_the_card():
    """If auto-load fails the file is still reachable for manual setup."""
    from custom_components.voice_jellyfin.frontend import async_register_frontend

    hass = _make_hass()
    with patch(
        "homeassistant.components.frontend.add_extra_js_url",
        side_effect=RuntimeError("frontend missing"),
    ):
        await async_register_frontend(hass)

    hass.http.async_register_static_paths.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_card_file_is_reported_not_raised():
    from custom_components.voice_jellyfin.frontend import async_register_frontend

    hass = _make_hass()
    with patch("pathlib.Path.is_file", return_value=False):
        await async_register_frontend(hass)

    hass.http.async_register_static_paths.assert_not_awaited()
    assert "voice_jellyfin_frontend_registered" not in hass.data


def test_shipped_card_file_actually_exists():
    """Guards against the card being moved without updating the loader."""
    from pathlib import Path

    import custom_components.voice_jellyfin.frontend as fe

    card = Path(fe.__file__).parent / "lovelace" / fe.CARD_FILENAME
    assert card.is_file(), f"card missing at {card}"
