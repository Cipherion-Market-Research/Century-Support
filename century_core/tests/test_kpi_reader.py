import pytest

from century_core.kpi_reader import BlockedKpiSourceError, KpiReader
from century_core.tests.conftest import utcnow_iso


async def test_read_returns_none_for_missing_key(fake_redis):
    reader = KpiReader(fake_redis)
    assert await reader.read("claim_api", "nonexistent") is None


async def test_read_returns_fresh_reading(fake_redis):
    fake_redis.seed_kpi("claim_api", "cipherions", 62, source_url="https://claim.ciphex.io/api/presale")
    reader = KpiReader(fake_redis)

    reading = await reader.read("claim_api", "cipherions")
    assert reading.value == 62
    assert reading.stale is False
    assert reading.source_url == "https://claim.ciphex.io/api/presale"


async def test_read_marks_old_fetched_at_as_stale(fake_redis):
    old_fetched_at = "2020-01-01T00:00:00Z"
    fake_redis.seed_kpi("claim_api", "cipherions", 62, fetched_at=old_fetched_at, stale_after_s=1800)
    reader = KpiReader(fake_redis)

    reading = await reader.read("claim_api", "cipherions")
    assert reading.stale is True


async def test_read_treats_recent_fetched_at_as_fresh(fake_redis):
    fake_redis.seed_kpi("claim_api", "cipherions", 62, fetched_at=utcnow_iso(), stale_after_s=1800)
    reader = KpiReader(fake_redis)

    reading = await reader.read("claim_api", "cipherions")
    assert reading.stale is False


async def test_abacus_index_source_is_blocked(fake_redis):
    fake_redis.seed_kpi("abacus_index", "latest", {"price": 1.0})
    reader = KpiReader(fake_redis)

    with pytest.raises(BlockedKpiSourceError):
        await reader.read("abacus_index", "latest")


async def test_abacus_index_health_is_also_blocked(fake_redis):
    reader = KpiReader(fake_redis)
    with pytest.raises(BlockedKpiSourceError):
        await reader.read_health("abacus_index")


async def test_onchain_base_source_is_blocked(fake_redis):
    fake_redis.seed_kpi("onchain_base", "token_price", 0.115)
    reader = KpiReader(fake_redis)

    with pytest.raises(BlockedKpiSourceError):
        await reader.read("onchain_base", "token_price")


async def test_onchain_base_health_is_also_blocked(fake_redis):
    reader = KpiReader(fake_redis)
    with pytest.raises(BlockedKpiSourceError):
        await reader.read_health("onchain_base")


async def test_read_health_returns_health_payload(fake_redis):
    await fake_redis.set(
        "kpi:claim_api:__health", '{"ok": true, "last_success": "2026-07-20T00:00:00Z", "consecutive_failures": 0}'
    )
    reader = KpiReader(fake_redis)
    health = await reader.read_health("claim_api")
    assert health["ok"] is True
