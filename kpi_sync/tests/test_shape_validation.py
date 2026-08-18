"""WP-7c: per-source payload shape validation.

Acceptance: a renamed/missing key in one source's fixture flips ONLY that
source to degraded (kpi:<source>:__health.ok=false, reason=shape_change,
plus a kpi:<source>:__shape status envelope) -- other sources, run in the
same cycle against their own correct fixtures, are entirely unaffected.
"""
import json

import pytest

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.pollers.ams_keymetrics import AmsKeyMetricsPoller
from kpi_sync.pollers.ams_marketing import AmsMarketingPoller
from kpi_sync.pollers.claim_api import ClaimApiPoller
from kpi_sync.ratelimiter import AsyncRateLimiter
from kpi_sync.shape_validation import missing_keys
from kpi_sync.tests.conftest import FakeResponse, FakeSession
from kpi_sync.tests.test_ams_keymetrics_poller import (
    KEY_METRICS_FIXTURE,
    PUBLIC_CHARTS_FIXTURE,
    PUBLIC_METRICS_FIXTURE,
)
from kpi_sync.tests.test_ams_marketing_poller import LIVE_FIXTURE as AMS_MARKETING_FIXTURE
from kpi_sync.tests.test_claim_api_poller import LIVE_FIXTURE as CLAIM_API_FIXTURE


def test_missing_keys_pure_function():
    assert missing_keys({"a": 1, "b": 2}, ("a", "b", "c")) == ["c"]
    assert missing_keys({"a": 1}, ("a",)) == []
    # Non-dict payloads report every expected key missing rather than
    # raising -- callers with list-shaped payloads use their own checks.
    assert missing_keys(["not", "a", "dict"], ("a", "b")) == ["a", "b"]


@pytest.mark.asyncio
async def test_claim_api_renamed_key_flips_only_claim_api_to_degraded(fake_redis):
    """`cipherions` renamed to `cipherion_count` in the upstream payload:
    claim_api must go degraded while an ams_marketing poller run in the
    same cycle against its own untouched fixture stays perfectly healthy."""
    store = KpiStore(fake_redis)

    broken_fixture = dict(CLAIM_API_FIXTURE)
    broken_fixture["cipherion_count"] = broken_fixture.pop("cipherions")

    claim_poller = ClaimApiPoller(store, FakeSession([FakeResponse(200, json_body=broken_fixture)]))
    await claim_poller.poll_once()

    claim_health = await store.read_health("claim_api")
    assert claim_health["ok"] is False
    assert claim_health["reason"] == "shape_change"
    # last_success is not advanced by a degraded cycle -- it stays None
    # (never yet had a clean success), matching the "not a confirmed-good
    # cycle" semantics.
    assert claim_health["last_success"] is None

    shape_status = json.loads(await fake_redis.get("kpi:claim_api:__shape"))
    assert shape_status["value"]["status"] == "degraded"
    assert shape_status["value"]["missing_keys"] == ["cipherions"]
    assert shape_status["source"] == Config.CLAIM_PORTAL_PUBLIC_URL

    # Partial data is still served best-effort -- degraded isn't "no data".
    price = json.loads(await fake_redis.get("kpi:claim_api:price"))
    assert price["value"] == {"ui": "$0.26", "raw": 0.26}

    # A second, independent, healthy source in the same cycle is untouched.
    ams_poller = AmsMarketingPoller(
        store,
        FakeSession([FakeResponse(200, json_body=AMS_MARKETING_FIXTURE)]),
        AsyncRateLimiter(max_calls=8, period_s=60.0),
    )
    await ams_poller.poll_once()
    ams_health = await store.read_health("ams_marketing")
    assert ams_health == {"ok": True, "last_success": ams_poller.last_success, "consecutive_failures": 0}
    assert "reason" not in ams_health
    assert await fake_redis.get("kpi:ams_marketing:__shape") is None


@pytest.mark.asyncio
async def test_ams_marketing_renamed_key_flips_only_that_source(fake_redis):
    store = KpiStore(fake_redis)
    broken = dict(AMS_MARKETING_FIXTURE)
    broken["trade_profitability_pct"] = broken.pop("trade_profitability")

    poller = AmsMarketingPoller(
        store, FakeSession([FakeResponse(200, json_body=broken)]), AsyncRateLimiter(8, 60.0)
    )
    await poller.poll_once()

    health = await store.read_health("ams_marketing")
    assert health["ok"] is False
    assert health["reason"] == "shape_change"

    shape_status = json.loads(await fake_redis.get("kpi:ams_marketing:__shape"))
    assert shape_status["value"]["missing_keys"] == ["trade_profitability"]

    # An unrelated, correctly-shaped claim_api fetch in the same fake_redis
    # instance is unaffected.
    claim_poller = ClaimApiPoller(store, FakeSession([FakeResponse(200, json_body=CLAIM_API_FIXTURE)]))
    await claim_poller.poll_once()
    claim_health = await store.read_health("claim_api")
    assert claim_health["ok"] is True
    assert "reason" not in claim_health


@pytest.mark.asyncio
async def test_ams_keymetrics_renamed_key_in_one_sub_fetch_degrades_whole_source(fake_redis):
    """ams_keymetrics makes three HTTP calls per cycle; a rename in just one
    of them (key_metrics: "metrics" -> "items") still degrades the shared
    ams_keymetrics source, while the two untouched sub-fetches still write
    their KPI values normally."""
    store = KpiStore(fake_redis)
    broken_key_metrics = dict(KEY_METRICS_FIXTURE)
    broken_key_metrics["items"] = broken_key_metrics.pop("metrics")

    poller = AmsKeyMetricsPoller(
        store,
        FakeSession(
            [
                FakeResponse(200, json_body=broken_key_metrics),
                FakeResponse(200, json_body=PUBLIC_METRICS_FIXTURE),
                FakeResponse(200, json_body=PUBLIC_CHARTS_FIXTURE),
            ]
        ),
        AsyncRateLimiter(8, 60.0),
    )
    await poller.poll_once()

    health = await store.read_health("ams_keymetrics")
    assert health["ok"] is False
    assert health["reason"] == "shape_change"

    shape_status = json.loads(await fake_redis.get("kpi:ams_keymetrics:__shape"))
    assert shape_status["value"]["missing_keys"] == {"key_metrics": ["metrics"]}

    # public_metrics/public_charts were shaped correctly and still wrote.
    public_metrics = json.loads(await fake_redis.get("kpi:ams_keymetrics:public_metrics"))
    assert public_metrics["value"]["drawdown"] == "-11.46%"


@pytest.mark.asyncio
async def test_shape_validation_disabled_flag_suppresses_the_check(fake_redis, monkeypatch):
    monkeypatch.setattr(Config, "SHAPE_VALIDATION_ENABLED", False)
    store = KpiStore(fake_redis)
    broken_fixture = dict(CLAIM_API_FIXTURE)
    broken_fixture["cipherion_count"] = broken_fixture.pop("cipherions")

    poller = ClaimApiPoller(store, FakeSession([FakeResponse(200, json_body=broken_fixture)]))
    await poller.poll_once()

    health = await store.read_health("claim_api")
    # Flag off -- no degradation is ever recorded, even for a genuinely
    # mismatched payload; plain success semantics apply.
    assert health == {"ok": True, "last_success": poller.last_success, "consecutive_failures": 0}
    assert await fake_redis.get("kpi:claim_api:__shape") is None
