import aiohttp
import pytest

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.main import build_pollers
from kpi_sync.pollers.abacus_index import AbacusIndexPoller


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
