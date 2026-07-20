"""Common poller lifecycle: run loop, per-cycle isolation, health tracking.

Every poller writes its own KPI keys in `fetch_and_store`; this base class
guarantees that one feed's failure never crashes the process, and that
`__health` always reflects the truth (never silently stays "ok").
"""
import asyncio
from typing import Optional

from kpi_sync.envelope import KpiStore, utcnow_iso
from kpi_sync.logging_setup import get_logger


class BasePoller:
    source_key: str = "override-me"
    interval_s: int = 60

    def __init__(self, store: KpiStore):
        self.store = store
        self.logger = get_logger(f"kpi_sync.poller.{self.source_key}")
        self.consecutive_failures = 0
        self.last_success: Optional[str] = None
        self._stopped = asyncio.Event()

    async def prime_from_existing_health(self) -> None:
        """Recover last_success/consecutive_failures across a restart so a
        crash-loop doesn't erase the record of how long a feed's been down."""
        existing = await self.store.read_health(self.source_key)
        if existing:
            self.last_success = existing.get("last_success")
            self.consecutive_failures = existing.get("consecutive_failures", 0) or 0

    async def fetch_and_store(self) -> None:
        raise NotImplementedError

    def get_interval_s(self) -> int:
        return self.interval_s

    async def poll_once(self) -> None:
        try:
            await self.fetch_and_store()
        except Exception:
            self.consecutive_failures += 1
            self.logger.error(
                "poll failed",
                extra={
                    "source_key": self.source_key,
                    "event": "poll_failure",
                    "consecutive_failures": self.consecutive_failures,
                },
                exc_info=True,
            )
            await self.store.write_health(
                self.source_key,
                ok=False,
                last_success=self.last_success,
                consecutive_failures=self.consecutive_failures,
            )
            return

        self.consecutive_failures = 0
        self.last_success = utcnow_iso()
        self.logger.info(
            "poll succeeded",
            extra={"source_key": self.source_key, "event": "poll_success"},
        )
        await self.store.write_health(
            self.source_key, ok=True, last_success=self.last_success, consecutive_failures=0
        )

    async def run_forever(self) -> None:
        await self.prime_from_existing_health()
        while not self._stopped.is_set():
            await self.poll_once()
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.get_interval_s())
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()
