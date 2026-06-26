"""Deep-link helpers for launching the Jellyfin Android TV app."""
from __future__ import annotations

import logging
from typing import Optional

from .adb import ADBController

_LOGGER = logging.getLogger(__name__)

JELLYFIN_PACKAGE = "org.jellyfin.androidtv"
JELLYFIN_MAIN_ACTIVITY = "org.jellyfin.androidtv.ui.startup.StartupActivity"

# Deep-link URI scheme used by the Jellyfin Android TV app
# https://github.com/jellyfin/jellyfin-androidtv
_DEEP_LINK_BASE = "jellyfin://"


async def async_launch_jellyfin(
    adb: ADBController,
    item_id: Optional[str] = None,
) -> None:
    """Launch the Jellyfin app on the target device.

    :param adb: An already-connected ADBController.
    :param item_id: Optional Jellyfin item ID to deep-link directly to.
                    If provided, opens that specific item; otherwise opens
                    the app home screen.
    """
    if item_id:
        uri = f"{_DEEP_LINK_BASE}openItem?id={item_id}"
        cmd = (
            f"am start "
            f"-a android.intent.action.VIEW "
            f"-d '{uri}' "
            f"-n {JELLYFIN_PACKAGE}/{JELLYFIN_MAIN_ACTIVITY}"
        )
        _LOGGER.debug("Deep-linking to Jellyfin item %s", item_id)
    else:
        cmd = (
            f"am start "
            f"-a android.intent.action.MAIN "
            f"-c android.intent.category.LAUNCHER "
            f"-n {JELLYFIN_PACKAGE}/{JELLYFIN_MAIN_ACTIVITY}"
        )
        _LOGGER.debug("Launching Jellyfin home screen")

    await adb.async_send_command(cmd)
