"""Authentication helpers for the Jellyfin API."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

_CLIENT_NAME = "VoiceJellyfin"
_CLIENT_VERSION = "0.1.0"
_DEVICE_NAME = "HomeAssistant"
_DEVICE_ID = "voice_jellyfin_ha"


@dataclass
class JellyfinAuth:
    """Holds Jellyfin connection credentials and builds auth headers."""

    url: str
    api_key: str = ""
    user_id: Optional[str] = None
    _access_token: str = field(default="", repr=False)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def base_url(self) -> str:
        """Return server base URL with trailing slash stripped."""
        return self.url.rstrip("/")

    def auth_headers(self) -> dict[str, str]:
        """Return headers required by every Jellyfin API request."""
        token = self._access_token or self.api_key
        authorization = (
            f'MediaBrowser Client="{_CLIENT_NAME}", '
            f'Device="{_DEVICE_NAME}", '
            f'DeviceId="{_DEVICE_ID}", '
            f'Version="{_CLIENT_VERSION}"'
        )
        if token:
            authorization += f', Token="{token}"'

        headers: dict[str, str] = {
            "X-Emby-Authorization": authorization,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if token:
            headers["X-Emby-Token"] = token
        return headers

    # ------------------------------------------------------------------
    # Username / password flow
    # ------------------------------------------------------------------

    async def async_authenticate(
        self, username: str, password: str
    ) -> str:
        """Authenticate with username + password; return the access token.

        Calls POST /Users/AuthenticateByName and stores the resulting
        access token internally so subsequent calls use it.
        """
        url = f"{self.base_url()}/Users/AuthenticateByName"
        payload = {"Username": username, "Pw": password}

        # Build minimal headers (no token yet)
        authorization = (
            f'MediaBrowser Client="{_CLIENT_NAME}", '
            f'Device="{_DEVICE_NAME}", '
            f'DeviceId="{_DEVICE_ID}", '
            f'Version="{_CLIENT_VERSION}"'
        )
        headers = {
            "X-Emby-Authorization": authorization,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()

        self._access_token = data["AccessToken"]
        self.user_id = data.get("User", {}).get("Id")
        _LOGGER.debug(
            "Jellyfin auth successful for user %s (id=%s)",
            username,
            self.user_id,
        )
        return self._access_token
