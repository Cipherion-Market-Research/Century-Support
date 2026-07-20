"""claim.ciphex.io/api/presale poller. §4.1: claim-center stats
(contributions, CPX presold/staked, claiming wallets, legacy price)."""
import aiohttp

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.http import fetch_json
from kpi_sync.pollers.base import BasePoller


class ClaimApiPoller(BasePoller):
    source_key = "claim_api"
    interval_s = Config.CLAIM_API_INTERVAL_S

    def __init__(self, store: KpiStore, session: aiohttp.ClientSession):
        super().__init__(store)
        self.session = session

    async def fetch_and_store(self) -> None:
        data = await fetch_json(self.session, Config.CLAIM_API_URL)
        # Upstream returns no timestamp of its own -- as_of is the C3-mandated
        # null, and fetched_at (stamped inside write_kpi) is the only
        # freshness signal consumers get for this source.
        await self.store.write_flat_metrics(
            self.source_key,
            data,
            source_url=Config.CLAIM_API_URL,
            as_of=None,
            ttl_s=Config.DEFAULT_TTL_S,
            stale_after_s=Config.DEFAULT_STALE_AFTER_S,
        )
