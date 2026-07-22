"""Deep-link helpers for launching the Jellyfin Android TV app."""
from __future__ import annotations

import logging
from typing import Optional

from .adb import ADBController

_LOGGER = logging.getLogger(__name__)

JELLYFIN_PACKAGE = "org.jellyfin.androidtv"
JELLYFIN_MAIN_ACTIVITY = "org.jellyfin.androidtv.ui.startup.StartupActivity"

_DEEP_LINK_BASE = "jellyfin://"

# Activity names for common Jellyfin client packages
_PACKAGE_ACTIVITIES: dict[str, str] = {
    "org.jellyfin.androidtv": "org.jellyfin.androidtv.ui.startup.StartupActivity",
    "org.jellyfin.mobile": "org.jellyfin.mobile.MainActivity",
}


async def async_launch_jellyfin(
    adb: ADBController,
    item_id: Optional[str] = None,
    package: str = JELLYFIN_PACKAGE,
) -> bool:
    """Launch the Jellyfin app on the target device. Returns True on success.

    :param adb: An already-connected ADBController.
    :param item_id: Optional Jellyfin item ID to deep-link directly to.
    :param package: Android package name of the Jellyfin client to launch.
    """
    activity = _PACKAGE_ACTIVITIES.get(package, f"{package}.ui.startup.StartupActivity")

    if item_id:
        uri = f"{_DEEP_LINK_BASE}openItem?id={item_id}"
        cmd = (
            f"am start "
            f"-a android.intent.action.VIEW "
            f"-d '{uri}' "
            f"-n {package}/{activity}"
        )
        _LOGGER.debug("Deep-linking to Jellyfin item %s via %s", item_id, package)
    else:
        cmd = (
            f"am start "
            f"-a android.intent.action.MAIN "
            f"-c android.intent.category.LAUNCHER "
            f"-n {package}/{activity}"
        )
        _LOGGER.debug("Launching Jellyfin home screen via %s", package)

    result = await adb.async_send_command(cmd)
    if result and ("error" in result.lower() or "exception" in result.lower()):
        _LOGGER.warning("Jellyfin launch may have failed (%s): %s", package, result)
        return False
    return True
