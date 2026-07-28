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
from kpi_sync.shape_validation import missing_keys


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
        # WP-7c: each sub-fetch is checked against its own expected shape;
        # problems are collected (keyed by sub-fetch name) and reported as
        # a single degraded cycle at the end rather than three competing
        # writes to the same kpi:ams_keymetrics:__shape key.
        problems = {}
        await self._store_key_metrics(problems)
        await self._store_public_metrics(problems)
        await self._store_public_charts(problems)
        if problems and Config.SHAPE_VALIDATION_ENABLED:
            await self.report_shape_degraded(problems, source_url=self.key_metrics_url)

    async def _store_key_metrics(self, problems: dict) -> None:
        data = await fetch_json(self.session, self.key_metrics_url, rate_limiter=self.rate_limiter)
        if Config.SHAPE_VALIDATION_ENABLED:
            missing = missing_keys(data, Config.AMS_KEY_METRICS_EXPECTED_KEYS)
            if missing:
                problems["key_metrics"] = missing
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

    async def _store_public_metrics(self, problems: dict) -> None:
        data = await fetch_json(self.session, self.public_metrics_url, rate_limiter=self.rate_limiter)
        if Config.SHAPE_VALIDATION_ENABLED:
            missing = missing_keys(data, Config.AMS_PUBLIC_METRICS_EXPECTED_KEYS)
            if missing:
                problems["public_metrics"] = missing
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

    async def _store_public_charts(self, problems: dict) -> None:
        data = await fetch_json(self.session, self.public_charts_url, rate_limiter=self.rate_limiter)
        if Config.SHAPE_VALIDATION_ENABLED:
            missing = missing_keys(data, Config.AMS_PUBLIC_CHARTS_EXPECTED_KEYS)
            if missing:
                problems["public_charts"] = missing
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
