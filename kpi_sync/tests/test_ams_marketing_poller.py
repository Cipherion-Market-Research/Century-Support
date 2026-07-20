import json

import pytest

from kpi_sync.envelope import KpiStore
from kpi_sync.pollers.ams_marketing import AmsMarketingPoller
from kpi_sync.ratelimiter import AsyncRateLimiter
from kpi_sync.tests.conftest import FakeResponse, FakeSession

# Captured live from https://ams.ciphex.io/api/ciphex-data/marketing-stats
# on 2026-07-20 (headers included x-ratelimit-limit: 10).
LIVE_FIXTURE = {
    "total_ra_return": {"value": 21.08, "24hchg": 0.26},
    "validation_accuracy": {"value": 75.44, "24hchg": 0.01},
    "trade_profitability": {"value": 58.76, "24hchg": 2.14},
    "last_updated": "7-10-2026 3:00 PM",
}


@pytest.mark.asyncio
async def test_ams_marketing_poller_parses_as_of_and_skips_raw_last_updated_key(fake_redis):
    store = KpiStore(fake_redis)
    session = FakeSession([FakeResponse(200, json_body=LIVE_FIXTURE)])
    limiter = AsyncRateLimiter(max_calls=8, period_s=60.0)
    poller = AmsMarketingPoller(store, session, limiter)

    await poller.fetch_and_store()

    validation = json.loads(await fake_redis.get("kpi:ams_marketing:validation_accuracy"))
    assert validation["value"] == {"value": 75.44, "24hchg": 0.01}
    assert validation["as_of"] == "2026-07-10T15:00:00"

    # The raw non-ISO last_updated string itself is not stored as its own
    # metric -- it was only consumed to populate as_of on the others.
    assert await fake_redis.get("kpi:ams_marketing:last_updated") is None
