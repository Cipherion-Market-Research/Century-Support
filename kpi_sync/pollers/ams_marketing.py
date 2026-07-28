"""ams.ciphex.io/api/ciphex-data/marketing-stats poller. §4.1: headline
Alpha KPIs (RA return, validation accuracy, P/L success + 24h deltas) --
the same feed the homepage uses. Rate-limited: shares the ams.* budget
with AmsKeyMetricsPoller via a common AsyncRateLimiter instance."""
import aiohttp

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.http import fetch_json
from kpi_sync.parsing import parse_upstream_datetime
from kpi_sync.pollers.base import BasePoller
from kpi_sync.ratelimiter import AsyncRateLimiter
from kpi_sync.shape_validation import missing_keys


class AmsMarketingPoller(BasePoller):
    source_key = "ams_marketing"
    interval_s = Config.AMS_MARKETING_INTERVAL_S

    def __init__(self, store: KpiStore, session: aiohttp.ClientSession, rate_limiter: AsyncRateLimiter):
        super().__init__(store)
        self.session = session
        self.rate_limiter = rate_limiter
        self.url = Config.AMS_BASE_URL + Config.AMS_MARKETING_STATS_PATH

    async def fetch_and_store(self) -> None:
        data = await fetch_json(self.session, self.url, rate_limiter=self.rate_limiter)
        if Config.SHAPE_VALIDATION_ENABLED:
            missing = missing_keys(data, Config.AMS_MARKETING_EXPECTED_KEYS)
            if missing:
                await self.report_shape_degraded(missing, source_url=self.url)
        as_of = parse_upstream_datetime(data.get("last_updated"))
        await self.store.write_flat_metrics(
            self.source_key,
            data,
            source_url=self.url,
            as_of=as_of,
            ttl_s=Config.DEFAULT_TTL_S,
            stale_after_s=Config.DEFAULT_STALE_AFTER_S,
            skip_keys={"last_updated"},
        )
