"""Read-side over the C3 KPI envelopes kpi_sync writes to Redis.

Deliberately does not modify kpi_sync/envelope.py (WP-3's delivered
module) — reuses its public static key-builder methods
(KpiStore.kpi_key / KpiStore.health_key) for DRY-ness and touches nothing
else there.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from kpi_sync.envelope import KpiStore

from century_core.config import Config


class BlockedKpiSourceError(Exception):
    """A KPI source the owner ruled internal-only was requested (Sprint-1:
    kpi:abacus_index:* must never reach a user-facing response). This is a
    programming error in a command/Q&A handler, not a runtime condition —
    it should never be reachable from a real request."""


@dataclass
class KpiReading:
    source: str
    metric: str
    value: Any
    unit: Optional[str]
    source_url: str
    as_of: Optional[str]
    fetched_at: str
    stale: bool


def _is_stale(envelope: dict) -> bool:
    """C3 rule: now - fetched_at > stale_after_s is STALE."""
    fetched_at = envelope.get("fetched_at")
    stale_after_s = envelope.get("stale_after_s")
    if fetched_at is None or stale_after_s is None:
        return False
    try:
        fetched_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    age_s = (datetime.now(timezone.utc) - fetched_dt).total_seconds()
    return age_s > stale_after_s


class KpiReader:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def read(self, source: str, metric: str) -> Optional[KpiReading]:
        if source in Config.BLOCKED_KPI_SOURCES:
            raise BlockedKpiSourceError(
                f"kpi:{source}:* is internal-only (owner ruling) and must never be served"
            )

        raw = await self.redis.get(KpiStore.kpi_key(source, metric))
        if raw is None:
            return None
        try:
            envelope = json.loads(raw)
        except (TypeError, ValueError):
            return None

        return KpiReading(
            source=source,
            metric=metric,
            value=envelope.get("value"),
            unit=envelope.get("unit"),
            source_url=envelope.get("source"),
            as_of=envelope.get("as_of"),
            fetched_at=envelope.get("fetched_at"),
            stale=_is_stale(envelope),
        )

    async def read_health(self, source: str) -> Optional[dict]:
        if source in Config.BLOCKED_KPI_SOURCES:
            raise BlockedKpiSourceError(f"kpi:{source}:__health is internal-only")
        raw = await self.redis.get(KpiStore.health_key(source))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None
