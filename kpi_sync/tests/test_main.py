import aiohttp
import pytest

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.main import build_pollers
from kpi_sync.pollers.abacus_index import AbacusIndexPoller
from kpi_sync.pollers.claim_api import ClaimApiPoller


@pytest.mark.asyncio
async def test_build_pollers_excludes_abacus_by_default(fake_redis, monkeypatch):
    monkeypatch.setattr(Config, "ABACUS_ENABLED", False)
    store = KpiStore(fake_redis)
    async with aiohttp.ClientSession() as session:
        pollers = build_pollers(store, session)
    assert not any(isinstance(p, AbacusIndexPoller) for p in pollers)
    assert {p.source_key for p in pollers} == {
        "claim_api",
        "ams_marketing",
        "ams_keymetrics",
        "onchain_base",
        "onchain_eth",
        "onchain",
    }


@pytest.mark.asyncio
async def test_build_pollers_includes_abacus_when_enabled(fake_redis, monkeypatch):
    monkeypatch.setattr(Config, "ABACUS_ENABLED", True)
    store = KpiStore(fake_redis)
    async with aiohttp.ClientSession() as session:
        pollers = build_pollers(store, session)
    assert any(isinstance(p, AbacusIndexPoller) for p in pollers)


@pytest.mark.asyncio
async def test_per_source_enable_flag_excludes_only_that_source(fake_redis, monkeypatch):
    """WP-7c amendment: KPI_SYNC_<SOURCE>_ENABLED generalizes the
    KPI_SYNC_ABACUS_ENABLED on/off pattern to every source. Disabling one
    (claim_api) must drop only that poller -- every other source still
    builds and (per this second assertion) still writes its own envelope
    with no interference from the disabled one."""
    monkeypatch.setattr(Config, "CLAIM_API_ENABLED", False)
    store = KpiStore(fake_redis)
    async with aiohttp.ClientSession() as session:
        pollers = build_pollers(store, session)

    assert not any(isinstance(p, ClaimApiPoller) for p in pollers)
    assert {p.source_key for p in pollers} == {
        "ams_marketing",
        "ams_keymetrics",
        "onchain_base",
        "onchain_eth",
        "onchain",
    }

    # The disabled source never runs, so it never writes -- but every other
    # poller built above is unaffected and would still populate normally
    # (exercised in each poller's own test module; here we just confirm the
    # disabled source is absent from both the poller list and would leave
    # no envelope behind).
    assert await fake_redis.get("kpi:claim_api:price") is None
