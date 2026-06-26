"""Direct ADB TCP controller using asyncio subprocess."""
from __future__ import annotations

import asyncio
import logging

_LOGGER = logging.getLogger(__name__)


class ADBController:
    """Controls an Android device over TCP ADB without the androidtv integration.

    Requires the ``adb`` binary to be available on the PATH where HA runs.
    The device must have TCP debugging enabled (``adb tcpip 5555``).
    """

    def __init__(self, host: str, port: int = 5555) -> None:
        self._host = host
        self._port = port
        self._target = f"{host}:{port}"

    async def async_connect(self) -> bool:
        """Connect to the device; returns True on success."""
        stdout = await self.async_send_command(f"connect {self._target}", shell=False)
        success = "connected" in stdout.lower()
        if success:
            _LOGGER.debug("ADB connected to %s", self._target)
        else:
            _LOGGER.warning("ADB connect failed: %s", stdout)
        return success

    async def async_send_command(
        self, cmd: str, shell: bool = True
    ) -> str:
        """Run an ADB command and return stdout as a string.

        :param cmd: Command string. When shell=True, prepended with
                    ``adb -s <target> shell``; otherwise run as plain adb args.
        :param shell: Whether to prepend ``shell`` to the adb invocation.
        """
        if shell:
            args = ["adb", "-s", self._target, "shell"] + cmd.split()
        else:
            args = ["adb"] + cmd.split()

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=10
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            if proc.returncode != 0:
                _LOGGER.debug("ADB stderr: %s", stderr_bytes.decode("utf-8").strip())
            return stdout
        except asyncio.TimeoutError:
            _LOGGER.warning("ADB command timed out: %s", cmd)
            return ""
        except FileNotFoundError:
            _LOGGER.error("'adb' binary not found on PATH")
            return ""
        except Exception as exc:
            _LOGGER.error("ADB command failed: %s — %s", cmd, exc)
            return ""

    async def async_key_event(self, keycode: int) -> None:
        """Send an Android key event by numeric keycode."""
        await self.async_send_command(f"input keyevent {keycode}")

    async def async_start_activity(
        self,
        package: str,
        activity: str | None = None,
    ) -> None:
        """Launch an activity via ``am start``.

        :param package: Android package name.
        :param activity: Fully-qualified activity name.  If omitted, the
                         package is started with the launcher intent.
        """
        if activity:
            cmd = f"am start -n {package}/{activity}"
        else:
            cmd = (
                f"am start "
                f"-a android.intent.action.MAIN "
                f"-c android.intent.category.LAUNCHER "
                f"-n {package}/.MainActivity"
            )
        await self.async_send_command(cmd)
