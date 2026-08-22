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
                _LOGGER.debug("ADB stderr: %s", stderr_bytes.decode("utf-8", errors="replace").strip())
            return stdout
        except asyncio.TimeoutError:
            _LOGGER.warning("ADB command timed out: %s", cmd)
            # Reap the hung process — otherwise each timeout leaks a zombie
            # adb subprocess and its pipe fds.
            try:
                proc.kill()
                await proc.communicate()
            except Exception:  # noqa: BLE001 — already timed out; nothing else to do
                pass
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


_KEYCODE_WAKEUP = 224


class ADBTVController:
    """TV controller speaking directly to a device over TCP ADB.

    Presents the same interface as AndroidTVController (async_send_key,
    async_launch_app, async_deep_link, async_wake, async_ensure_awake) so the
    coordinator can use it when no media_player entity is configured — e.g.
    a Fire TV without the androidtv integration.
    """

    def __init__(self, host: str, port: int = 5555) -> None:
        self._adb = ADBController(host, port)
        self._target = f"{host}:{port}"
        self._connected = False

    async def _ensure_connected(self) -> bool:
        if not self._connected:
            self._connected = await self._adb.async_connect()
        return self._connected

    async def async_send_key(self, key: str, repeat: int = 1) -> None:
        from .remote import KEY_MAP
        keycode = KEY_MAP.get(key)
        if keycode is None:
            _LOGGER.warning("Unknown key for ADB TV: %s", key)
            return
        await self._ensure_connected()
        for _ in range(repeat):
            await self._adb.async_key_event(keycode)

    async def async_launch_app(self, package_name: str) -> bool:
        from .deep_link import async_launch_jellyfin
        await self._ensure_connected()
        return await async_launch_jellyfin(self._adb, package=package_name)

    async def async_deep_link(self, uri: str, package: str | None = None) -> bool:
        await self._ensure_connected()
        cmd = f"am start -a android.intent.action.VIEW -d '{uri}'"
        if package:
            cmd += f" -p {package}"
        result = await self._adb.async_send_command(cmd)
        return not ("error" in result.lower() or "exception" in result.lower())

    async def async_wake(self) -> None:
        await self._ensure_connected()
        await self._adb.async_key_event(_KEYCODE_WAKEUP)

    async def async_ensure_awake(self, timeout: float = 30.0) -> bool:
        ok = await self._ensure_connected()
        if ok:
            await self._adb.async_key_event(_KEYCODE_WAKEUP)
        return ok
