"""C3 envelope construction and Redis I/O.

Implements docs/CONTRACTS.md C3 verbatim: key convention
`kpi:<source>:<metric>`, the envelope value shape, and the `__health`
sidecar key each poller must maintain.
"""
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from kpi_sync.parsing import camel_to_snake


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class KpiEnvelope:
    value: Any
    unit: Optional[str]
    source: str  # url of the upstream feed (C3 field name, not the kpi: key segment)
    as_of: Optional[str]  # upstream's own timestamp, ISO-8601, or None if it doesn't provide one
    fetched_at: str
    ttl_s: int
    stale_after_s: int

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class KpiStore:
    """Thin wrapper over an async Redis client implementing the C3 contract."""

    def __init__(self, redis_client):
        self.redis = redis_client

    @staticmethod
    def kpi_key(source_key: str, metric: str) -> str:
        return f"kpi:{source_key}:{metric}"

    @staticmethod
    def health_key(source_key: str) -> str:
        return f"kpi:{source_key}:__health"

    async def write_kpi(
        self,
        source_key: str,
        metric: str,
        value: Any,
        *,
        source_url: str,
        unit: Optional[str] = None,
        as_of: Optional[str] = None,
        ttl_s: int,
        stale_after_s: int,
    ) -> None:
        envelope = KpiEnvelope(
            value=value,
            unit=unit,
            source=source_url,
            as_of=as_of,
            fetched_at=utcnow_iso(),
            ttl_s=ttl_s,
            stale_after_s=stale_after_s,
        )
        # ttl_s must outlive stale_after_s: consumers use the key's presence
        # to distinguish "stale" (fetched_at present but old) from "never
        # existed" (key expired and gone). Enforced here, not trusted from
        # callers, since it's the one invariant the whole staleness design
        # depends on.
        ex = max(ttl_s, stale_after_s + 1)
        await self.redis.set(self.kpi_key(source_key, metric), envelope.to_json(), ex=ex)

    async def read_health(self, source_key: str) -> Optional[dict]:
        raw = await self.redis.get(self.health_key(source_key))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    async def write_health(
        self,
        source_key: str,
        *,
        ok: bool,
        last_success: Optional[str],
        consecutive_failures: int,
        reason: Optional[str] = None,
    ) -> None:
        payload = {
            "ok": ok,
            "last_success": last_success,
            "consecutive_failures": consecutive_failures,
        }
        # `reason` is additive and omitted entirely when not given, so every
        # pre-existing caller (plain success/failure) still writes the
        # original 3-key C3 __health shape verbatim. Used today for
        # WP-7c shape-degradation ("shape_change") -- see shape_validation.py.
        if reason is not None:
            payload["reason"] = reason
        # No expiry: a dead poller's last known health must stay readable
        # (that's the whole point of __health), not vanish on a TTL.
        await self.redis.set(self.health_key(source_key), json.dumps(payload))

    async def write_flat_metrics(
        self,
        source_key: str,
        data: dict,
        *,
        source_url: str,
        as_of: Optional[str],
        ttl_s: int,
        stale_after_s: int,
        skip_keys: Iterable[str] = (),
    ) -> None:
        """Write one KPI key per top-level field of a flat upstream dict,
        snake_casing the field name. Keeps the sync layer from having to
        hardcode (and silently drift from) the exact field set an upstream
        JSON API happens to expose today."""
        skip = set(skip_keys)
        for key, value in data.items():
            if key in skip:
                continue
            await self.write_kpi(
                source_key,
                camel_to_snake(key),
                value,
                source_url=source_url,
                as_of=as_of,
                ttl_s=ttl_s,
                stale_after_s=stale_after_s,
            )
