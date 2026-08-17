"""Shared test doubles: an in-memory fake Redis (C3 envelope shape) and a
stub-store-backed Stores fixture, so the whole suite runs without real
Redis/Postgres/OpenAI -- WP-5 acceptance: "test suite green with stubbed
stores."
"""
import json
from datetime import datetime, timezone
from typing import Dict, Optional

import pytest

from century_core.kpi_reader import KpiReader
from century_core.llm import StubLLMProvider
from century_core.stores import Stores
from facts_store import default_store
from kpi_sync.envelope import KpiStore


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class FakeRedis:
    """Minimal async-Redis double: get/set/rpush/ping, enough for
    KpiReader + /v1/broadcasts. Not a general Redis emulator."""

    def __init__(self):
        self._data: Dict[str, str] = {}
        self._lists: Dict[str, list] = {}

    async def get(self, key: str) -> Optional[str]:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        self._data[key] = value

    async def rpush(self, key: str, value: str) -> None:
        self._lists.setdefault(key, []).append(value)

    async def ping(self) -> bool:
        return True

    def seed_kpi(
        self,
        source: str,
        metric: str,
        value,
        *,
        unit=None,
        source_url="https://example.ciphex.io/feed",
        as_of=None,
        fetched_at=None,
        ttl_s=3600,
        stale_after_s=1800,
    ) -> None:
        envelope = {
            "value": value,
            "unit": unit,
            "source": source_url,
            "as_of": as_of,
            "fetched_at": fetched_at or utcnow_iso(),
            "ttl_s": ttl_s,
            "stale_after_s": stale_after_s,
        }
        self._data[KpiStore.kpi_key(source, metric)] = json.dumps(envelope)


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def facts():
    return default_store()


@pytest.fixture
def stub_llm():
    return StubLLMProvider()


@pytest.fixture
def stub_stores(facts, fake_redis, stub_llm):
    return Stores(facts=facts, kpi=KpiReader(fake_redis), llm=stub_llm, rag_conn=None, rag_provider=None)


class OverlayFactsStore:
    """Wraps a real FactsStore and overlays/masks specific keys, so tests
    can exercise a contract fact key's "present" or "absent" branch without
    needing to edit the committed facts.yaml -- e.g. simulating a contract
    key (identity.listing_initiative, round-terms.new_round_max_contribution,
    etc.) that a parallel agent may add on another branch, or forcing a key
    that IS present today to look absent/unknown to exercise the fallback
    path. `overrides[key] = <Fact instance>` injects/replaces a key;
    `overrides[key] = None` makes `get(key)` return None (absent) regardless
    of the delegate."""

    def __init__(self, delegate, overrides: Dict[str, object]):
        self._delegate = delegate
        self._overrides = overrides

    def get(self, key):
        if key in self._overrides:
            return self._overrides[key]
        return self._delegate.get(key)

    def __contains__(self, key):
        if key in self._overrides:
            return self._overrides[key] is not None
        return key in self._delegate

    def __len__(self):
        return len(self._delegate)

    def keys(self):
        return self._delegate.keys()


@pytest.fixture
def make_overlay_stores(stub_stores):
    """Factory fixture: make_overlay_stores({"identity.listing_initiative": some_fact, ...})
    returns a Stores whose facts store overlays those keys on top of the
    real facts.yaml-backed store, everything else (kpi/llm) unchanged."""
    from dataclasses import replace

    def _make(overrides: Dict[str, object]):
        return replace(stub_stores, facts=OverlayFactsStore(stub_stores.facts, overrides))

    return _make


def make_fact(value, *, verified_on="2026-08-17", source_url="https://ciphex.io/", notes=None):
    """Build a facts_store.schema.Fact for injection via OverlayFactsStore."""
    from facts_store import Fact

    return Fact(value=value, verified_on=verified_on, source_url=source_url, notes=notes)
