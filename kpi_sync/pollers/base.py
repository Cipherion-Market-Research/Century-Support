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
        # Set by mark_degraded()/report_shape_degraded() during
        # fetch_and_store() when the fetch itself succeeded but the payload
        # failed a soft check (currently: shape validation). Reset every
        # cycle in poll_once() below -- see shape_validation.py.
        self._degraded_reason: Optional[str] = None

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

    def mark_degraded(self, reason: str) -> None:
        """Called by a subclass's fetch_and_store() when the HTTP fetch
        itself succeeded but the payload failed a soft check (e.g. shape
        validation). Does not raise: poll_once() below still treats this as
        a completed cycle (no consecutive_failures bump, no exception log),
        but records __health.ok=false with `reason` instead of a plain
        success, and leaves last_success at its prior value -- a degraded
        cycle is not a confirmed-good one."""
        self._degraded_reason = reason

    async def report_shape_degraded(self, missing, *, source_url: str) -> None:
        """Shape-validation-specific helper: writes the `kpi:<source>:__shape`
        status envelope (through the normal C3 envelope path -- same
        KpiEnvelope shape, not a new schema) and flags the cycle via
        mark_degraded("shape_change"). `missing` is either a flat list of
        missing top-level keys, or (for a poller that makes more than one
        HTTP call per cycle, e.g. ams_keymetrics) a dict keyed by sub-fetch
        name."""
        self.logger.warning(
            "payload shape degraded: missing expected keys",
            extra={
                "source_key": self.source_key,
                "event": "shape_degraded",
                "missing_keys": missing,
            },
        )
        await self.store.write_kpi(
            self.source_key,
            "__shape",
            {"status": "degraded", "missing_keys": missing},
            source_url=source_url,
            as_of=None,
            ttl_s=self.store_ttl_s(),
            stale_after_s=self.store_stale_after_s(),
        )
        self.mark_degraded("shape_change")

    @staticmethod
    def store_ttl_s() -> int:
        from kpi_sync.config import Config

        return Config.DEFAULT_TTL_S

    @staticmethod
    def store_stale_after_s() -> int:
        from kpi_sync.config import Config

        return Config.DEFAULT_STALE_AFTER_S

    async def poll_once(self) -> None:
        self._degraded_reason = None
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

        if self._degraded_reason is not None:
            self.logger.warning(
                "poll succeeded but payload degraded",
                extra={
                    "source_key": self.source_key,
                    "event": "poll_degraded",
                    "reason": self._degraded_reason,
                },
            )
            await self.store.write_health(
                self.source_key,
                ok=False,
                last_success=self.last_success,
                consecutive_failures=self.consecutive_failures,
                reason=self._degraded_reason,
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
