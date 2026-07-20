"""Abacus Indexer /v0/latest poller. §4.1: composite BTC/ETH price + 1-min
OHLCV with venue provenance.

OQ-4: the Indexer is only reachable at a raw ALB hostname today (its TLS
cert doesn't even cover that hostname -- it's issued for api.ciphex.io).
Config.ABACUS_BASE_URL is the single knob this poller depends on; nothing
here hardcodes the ALB name so flipping to a stable subdomain later is a
config change, not a code change.

Amendment C-R1 (owner adjudication, 2026-07-20): the owner does not want
Abacus Indexer data exposed publicly. This poller is therefore
DISABLED BY DEFAULT (Config.ABACUS_ENABLED, see main.build_pollers()) --
the code stays in place for when it's cleared, but does not run unless
KPI_SYNC_ABACUS_ENABLED=true is set. Even once enabled for internal use,
every `kpi:abacus_index:*` key is INTERNAL-ONLY pending owner/legal
clearance: WP-5 (Century Core) must never surface these values, directly
or derived, in a user-facing response.
"""
from datetime import datetime, timezone

import aiohttp

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.http import fetch_json
from kpi_sync.pollers.base import BasePoller


def _epoch_to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


class AbacusIndexPoller(BasePoller):
    source_key = "abacus_index"
    interval_s = Config.ABACUS_INTERVAL_S

    def __init__(self, store: KpiStore, session: aiohttp.ClientSession):
        super().__init__(store)
        self.session = session
        self.url = Config.ABACUS_BASE_URL + Config.ABACUS_LATEST_PATH

    async def fetch_and_store(self) -> None:
        data = await fetch_json(self.session, self.url)
        if not isinstance(data, list):
            raise ValueError(f"expected a list from {self.url}, got {type(data).__name__}")

        for entry in data:
            asset = entry.get("asset")
            market_type = entry.get("market_type")
            if not asset or not market_type:
                continue
            metric = f"{asset.lower()}_{market_type.lower()}"
            as_of = _epoch_to_iso(entry["time"]) if entry.get("time") is not None else None
            await self.store.write_kpi(
                self.source_key,
                metric,
                entry,
                unit="USD",
                source_url=self.url,
                as_of=as_of,
                ttl_s=Config.DEFAULT_TTL_S,
                stale_after_s=Config.DEFAULT_STALE_AFTER_S,
            )
