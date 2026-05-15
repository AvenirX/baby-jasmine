from __future__ import annotations

import asyncio
import logging
import socket

logger = logging.getLogger(__name__)

_CHECK_HOST = "8.8.8.8"
_CHECK_PORT = 53
_POLL_INTERVAL = 5.0


def _tcp_probe(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


class NetworkMonitor:
    """Polls DNS every few seconds; broadcasts network up/down transitions."""

    def __init__(self) -> None:
        self._up = asyncio.Event()
        self._up.set()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start background polling (idempotent)."""
        if self._task is None or self._task.done():
            self._task = asyncio.get_event_loop().create_task(
                self._poll_loop(), name="network-monitor"
            )

    async def _poll_loop(self) -> None:
        while True:
            reachable = await asyncio.to_thread(_tcp_probe, _CHECK_HOST, _CHECK_PORT)
            if reachable and not self._up.is_set():
                logger.info("[Network] Connection restored")
                self._up.set()
            elif not reachable and self._up.is_set():
                logger.warning("[Network] Connection lost")
                self._up.clear()
            await asyncio.sleep(_POLL_INTERVAL)

    async def wait_for_up(self) -> None:
        """Return immediately if network is up; otherwise wait until it is."""
        await self._up.wait()


_monitor: NetworkMonitor | None = None


def get_monitor() -> NetworkMonitor:
    global _monitor
    if _monitor is None:
        _monitor = NetworkMonitor()
    return _monitor
