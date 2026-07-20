import json

import pytest

from kpi_sync.envelope import KpiStore


@pytest.mark.asyncio
async def test_write_kpi_shape_and_ttl(fake_redis):
    store = KpiStore(fake_redis)
    await store.write_kpi(
        "claim_api",
        "price",
        {"ui": "$0.26", "raw": 0.26},
        source_url="https://claim.ciphex.io/api/presale",
        as_of=None,
        ttl_s=3600,
        stale_after_s=1800,
    )
    raw = await fake_redis.get("kpi:claim_api:price")
    envelope = json.loads(raw)
    assert envelope["value"] == {"ui": "$0.26", "raw": 0.26}
    assert envelope["source"] == "https://claim.ciphex.io/api/presale"
    assert envelope["as_of"] is None
    assert envelope["ttl_s"] == 3600
    assert envelope["stale_after_s"] == 1800
    assert "fetched_at" in envelope and envelope["fetched_at"].endswith("Z")


@pytest.mark.asyncio
async def test_ttl_never_shorter_than_stale_after(fake_redis):
    store = KpiStore(fake_redis)
    # ttl_s intentionally shorter than stale_after_s: the key must still
    # outlive stale_after_s, or "stale" and "never existed" become
    # indistinguishable to a consumer.
    await store.write_kpi(
        "abacus_index",
        "btc_spot",
        {"price": 1},
        source_url="http://example",
        as_of=None,
        ttl_s=10,
        stale_after_s=1800,
    )
    assert fake_redis._expires_at["kpi:abacus_index:btc_spot"] > 1800 - 1


@pytest.mark.asyncio
async def test_write_flat_metrics_writes_one_key_per_field_and_skips(fake_redis):
    store = KpiStore(fake_redis)
    data = {
        "totalContributions": {"ui": "$1.82M", "raw": 1818927.09},
        "cipherions": 62,
        "last_updated": "should be skipped",
    }
    await store.write_flat_metrics(
        "claim_api",
        data,
        source_url="https://claim.ciphex.io/api/presale",
        as_of="2026-07-20T00:00:00Z",
        ttl_s=3600,
        stale_after_s=1800,
        skip_keys={"last_updated"},
    )
    assert await fake_redis.get("kpi:claim_api:total_contributions") is not None
    assert await fake_redis.get("kpi:claim_api:cipherions") is not None
    assert await fake_redis.get("kpi:claim_api:last_updated") is None

    envelope = json.loads(await fake_redis.get("kpi:claim_api:cipherions"))
    assert envelope["value"] == 62
    assert envelope["as_of"] == "2026-07-20T00:00:00Z"


@pytest.mark.asyncio
async def test_health_write_read_round_trip(fake_redis):
    store = KpiStore(fake_redis)
    assert await store.read_health("abacus_index") is None

    await store.write_health("abacus_index", ok=True, last_success="2026-07-20T17:00:00Z", consecutive_failures=0)
    status = await store.read_health("abacus_index")
    assert status == {"ok": True, "last_success": "2026-07-20T17:00:00Z", "consecutive_failures": 0}

    await store.write_health("abacus_index", ok=False, last_success="2026-07-20T17:00:00Z", consecutive_failures=3)
    status = await store.read_health("abacus_index")
    assert status["ok"] is False
    assert status["consecutive_failures"] == 3
    # last_success must survive a failed cycle -- it's the record of when
    # the feed last actually worked, not "now".
    assert status["last_success"] == "2026-07-20T17:00:00Z"
