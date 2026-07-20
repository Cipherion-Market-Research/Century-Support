"""ams.ciphex.io key-metrics + public-metrics + public-charts poller.
§4.1: full public KPI card set (MDD, YTD return, CRE, monthly periods).
All three live under the C3 source `ams_keymetrics` and share the same
30-min cadence and the ams.* rate-limit budget."""
import aiohttp

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.http import fetch_json
from kpi_sync.parsing import parse_upstream_datetime, parse_sheet_response
from kpi_sync.pollers.base import BasePoller
from kpi_sync.ratelimiter import AsyncRateLimiter


class AmsKeyMetricsPoller(BasePoller):
    source_key = "ams_keymetrics"
    interval_s = Config.AMS_KEYMETRICS_INTERVAL_S

    def __init__(self, store: KpiStore, session: aiohttp.ClientSession, rate_limiter: AsyncRateLimiter):
        super().__init__(store)
        self.session = session
        self.rate_limiter = rate_limiter
        self.key_metrics_url = Config.AMS_BASE_URL + Config.AMS_KEY_METRICS_PATH
        self.public_metrics_url = Config.AMS_BASE_URL + Config.AMS_PUBLIC_METRICS_PATH
        self.public_charts_url = Config.AMS_BASE_URL + Config.AMS_PUBLIC_CHARTS_PATH

    async def fetch_and_store(self) -> None:
        # Sequential, not parallel: all three share one rate-limit budget,
        # and the limiter already serializes/paces the underlying requests.
        await self._store_key_metrics()
        await self._store_public_metrics()
        await self._store_public_charts()

    async def _store_key_metrics(self) -> None:
        data = await fetch_json(self.session, self.key_metrics_url, rate_limiter=self.rate_limiter)
        as_of = parse_upstream_datetime(data.get("lastUpdated"))
        await self.store.write_kpi(
            self.source_key,
            "key_metrics",
            data.get("metrics", []),
            source_url=self.key_metrics_url,
            as_of=as_of,
            ttl_s=Config.DEFAULT_TTL_S,
            stale_after_s=Config.DEFAULT_STALE_AFTER_S,
        )

    async def _store_public_metrics(self) -> None:
        data = await fetch_json(self.session, self.public_metrics_url, rate_limiter=self.rate_limiter)
        rows = parse_sheet_response(data)
        latest = rows[-1] if rows else {}
        as_of = parse_upstream_datetime(latest.get("latestDate"))
        await self.store.write_kpi(
            self.source_key,
            "public_metrics",
            latest,
            source_url=self.public_metrics_url,
            as_of=as_of,
            ttl_s=Config.DEFAULT_TTL_S,
            stale_after_s=Config.DEFAULT_STALE_AFTER_S,
        )

    async def _store_public_charts(self) -> None:
        data = await fetch_json(self.session, self.public_charts_url, rate_limiter=self.rate_limiter)
        rows = parse_sheet_response(data)
        latest = rows[-1] if rows else {}
        as_of = parse_upstream_datetime(latest.get("date"))
        await self.store.write_kpi(
            self.source_key,
            "public_charts",
            rows,
            source_url=self.public_charts_url,
            as_of=as_of,
            ttl_s=Config.DEFAULT_TTL_S,
            stale_after_s=Config.DEFAULT_STALE_AFTER_S,
        )
