from kpi_sync.config import Config
from kpi_sync.health_server import active_sources


def test_abacus_excluded_from_health_by_default(monkeypatch):
    monkeypatch.setattr(Config, "ABACUS_ENABLED", False)
    assert "abacus_index" not in active_sources()
    assert set(active_sources()) == {
        "claim_api",
        "ams_marketing",
        "ams_keymetrics",
        "onchain_base",
        "onchain_eth",
        "onchain",
    }


def test_abacus_included_when_enabled(monkeypatch):
    monkeypatch.setattr(Config, "ABACUS_ENABLED", True)
    assert "abacus_index" in active_sources()
