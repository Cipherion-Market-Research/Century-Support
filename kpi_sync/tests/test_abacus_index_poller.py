import json

import pytest

from kpi_sync.envelope import KpiStore
from kpi_sync.pollers.abacus_index import AbacusIndexPoller
from kpi_sync.tests.conftest import FakeResponse, FakeSession

# Shape captured live from the Abacus Indexer ALB /v0/latest on 2026-07-20
# (plain HTTP -- its TLS cert is issued for a different hostname; see OQ-4).
LIVE_FIXTURE = [
    {
        "asset": "BTC",
        "market_type": "spot",
        "price": 65479.22,
        "time": 1784566958,
        "degraded": False,
        "included_venues": ["binance", "coinbase", "kraken", "okx"],
        "last_bar": {"open": 65495.035, "close": 65487.4},
    },
    {
        "asset": "BTC",
        "market_type": "perp",
        "price": None,
        "time": 1784566958,
        "degraded": False,
    },
    {
        "asset": "ETH",
        "market_type": "spot",
        "price": 1897.69,
        "time": 1784566958,
        "degraded": False,
    },
]


@pytest.mark.asyncio
async def test_abacus_index_poller_writes_one_metric_per_asset_market_pair(fake_redis):
    store = KpiStore(fake_redis)
    session = FakeSession([FakeResponse(200, json_body=LIVE_FIXTURE)])
    poller = AbacusIndexPoller(store, session)

    await poller.fetch_and_store()

    btc_spot = json.loads(await fake_redis.get("kpi:abacus_index:btc_spot"))
    assert btc_spot["value"]["price"] == 65479.22
    assert btc_spot["unit"] == "USD"
    # epoch 1784566958 -> ISO
    assert btc_spot["as_of"] == "2026-07-20T17:02:38Z"

    btc_perp = json.loads(await fake_redis.get("kpi:abacus_index:btc_perp"))
    assert btc_perp["value"]["price"] is None

    eth_spot = json.loads(await fake_redis.get("kpi:abacus_index:eth_spot"))
    assert eth_spot["value"]["price"] == 1897.69


@pytest.mark.asyncio
async def test_abacus_index_poller_rejects_non_list_payload(fake_redis):
    store = KpiStore(fake_redis)
    session = FakeSession([FakeResponse(200, json_body={"unexpected": "shape"})])
    poller = AbacusIndexPoller(store, session)

    with pytest.raises(ValueError):
        await poller.fetch_and_store()
