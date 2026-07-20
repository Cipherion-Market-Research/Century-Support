import json

import pytest

from kpi_sync.envelope import KpiStore
from kpi_sync.pollers.claim_api import ClaimApiPoller
from kpi_sync.tests.conftest import FakeResponse, FakeSession

# Captured live from https://claim.ciphex.io/api/presale on 2026-07-20.
LIVE_FIXTURE = {
    "totalContributions": {"ui": "$1.82M", "raw": 1818927.091866},
    "totalCPXPresold": {"ui": "15.88M", "raw": 15879640.661068216},
    "totalStaked": {"ui": "15.88M", "raw": 15879640.661068216},
    "percentStaked": {"ui": "15.12", "raw": 15.123467296255445},
    "cipherions": 62,
    "price": {"ui": "$0.26", "raw": 0.26},
    "contract": {
        "totalContributions": {"ui": "$27.30M", "raw": 27300000},
        "totalCPXPresold": {"ui": "105M", "raw": 105000000},
        "totalStaked": {"ui": "110.68M", "raw": 110681468.54427974},
        "percentStaked": {"ui": "105.41", "raw": 105.41092242312355},
    },
}


@pytest.mark.asyncio
async def test_claim_api_poller_writes_per_field_metrics_with_null_as_of(fake_redis):
    store = KpiStore(fake_redis)
    session = FakeSession([FakeResponse(200, json_body=LIVE_FIXTURE)])
    poller = ClaimApiPoller(store, session)

    await poller.fetch_and_store()

    price = json.loads(await fake_redis.get("kpi:claim_api:price"))
    assert price["value"] == {"ui": "$0.26", "raw": 0.26}
    assert price["as_of"] is None  # upstream provides no timestamp of its own
    assert price["source"] == "https://claim.ciphex.io/api/presale"

    cipherions = json.loads(await fake_redis.get("kpi:claim_api:cipherions"))
    assert cipherions["value"] == 62

    contract = json.loads(await fake_redis.get("kpi:claim_api:contract"))
    assert contract["value"]["totalCPXPresold"] == {"ui": "105M", "raw": 105000000}
