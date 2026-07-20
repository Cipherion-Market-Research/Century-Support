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
