"""claim.ciphex.io/api/presale poller. §4.1: claim-center stats
(contributions, CPX presold/staked, claiming wallets, legacy price)."""
import aiohttp

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.http import fetch_json
from kpi_sync.pollers.base import BasePoller
from kpi_sync.shape_validation import missing_keys


class ClaimApiPoller(BasePoller):
    source_key = "claim_api"
    interval_s = Config.CLAIM_API_INTERVAL_S

    def __init__(self, store: KpiStore, session: aiohttp.ClientSession):
        super().__init__(store)
        self.session = session

    async def fetch_and_store(self) -> None:
        data = await fetch_json(self.session, Config.CLAIM_API_URL)
        # WP-7c: a successful fetch missing a declared top-level key marks
        # this cycle degraded (kpi:claim_api:__shape + __health reason)
        # rather than silently serving whatever fields happen to remain.
        if Config.SHAPE_VALIDATION_ENABLED:
            missing = missing_keys(data, Config.CLAIM_API_EXPECTED_KEYS)
            if missing:
                await self.report_shape_degraded(missing, source_url=Config.CLAIM_PORTAL_PUBLIC_URL)
        # Upstream returns no timestamp of its own -- as_of is the C3-mandated
        # null, and fetched_at (stamped inside write_kpi) is the only
        # freshness signal consumers get for this source.
        await self.store.write_flat_metrics(
            self.source_key,
            data,
            source_url=Config.CLAIM_PORTAL_PUBLIC_URL,
            as_of=None,
            ttl_s=Config.DEFAULT_TTL_S,
            stale_after_s=Config.DEFAULT_STALE_AFTER_S,
        )
