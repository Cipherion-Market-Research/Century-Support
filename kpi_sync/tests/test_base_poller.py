import json

import pytest

from kpi_sync.envelope import KpiStore
from kpi_sync.pollers.base import BasePoller


class ScriptedPoller(BasePoller):
    source_key = "test_source"
    interval_s = 9999  # irrelevant here -- tests drive poll_once() directly

    def __init__(self, store, script):
        super().__init__(store)
        self.script = list(script)
        self.calls = 0

    async def fetch_and_store(self):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        await self.store.write_kpi(
            self.source_key,
            "value",
            step,
            source_url="http://example",
            as_of=None,
            ttl_s=3600,
            stale_after_s=1800,
        )


@pytest.mark.asyncio
async def test_success_then_kill_marks_health_not_the_envelope(fake_redis):
    """The core WP-3 acceptance line: a killed feed is marked stale via
    __health, and the last-good KPI envelope is left exactly as it was --
    never silently rewritten with a fresh fetched_at to hide the outage."""
    store = KpiStore(fake_redis)
    poller = ScriptedPoller(store, script=[{"n": 1}, RuntimeError("upstream down")])

    await poller.poll_once()
    envelope_after_success = json.loads(await fake_redis.get("kpi:test_source:value"))
    health_after_success = await store.read_health("test_source")
    assert envelope_after_success["value"] == {"n": 1}
    assert health_after_success == {
        "ok": True,
        "last_success": poller.last_success,
        "consecutive_failures": 0,
    }

    await poller.poll_once()  # this cycle raises
    envelope_after_kill = json.loads(await fake_redis.get("kpi:test_source:value"))
    health_after_kill = await store.read_health("test_source")

    # The envelope must be untouched: same fetched_at as the last real success.
    assert envelope_after_kill == envelope_after_success
    # But health must immediately reflect the failure.
    assert health_after_kill["ok"] is False
    assert health_after_kill["consecutive_failures"] == 1
    assert health_after_kill["last_success"] == health_after_success["last_success"]


@pytest.mark.asyncio
async def test_consecutive_failures_increment_across_cycles(fake_redis):
    store = KpiStore(fake_redis)
    poller = ScriptedPoller(
        store, script=[RuntimeError("down"), RuntimeError("still down"), RuntimeError("still down")]
    )
    for expected in (1, 2, 3):
        await poller.poll_once()
        health = await store.read_health("test_source")
        assert health["consecutive_failures"] == expected
        assert health["ok"] is False


@pytest.mark.asyncio
async def test_recovery_resets_consecutive_failures(fake_redis):
    store = KpiStore(fake_redis)
    poller = ScriptedPoller(store, script=[RuntimeError("down"), RuntimeError("down"), {"n": 2}])
    await poller.poll_once()
    await poller.poll_once()
    assert (await store.read_health("test_source"))["consecutive_failures"] == 2

    await poller.poll_once()
    health = await store.read_health("test_source")
    assert health["ok"] is True
    assert health["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_prime_from_existing_health_survives_restart(fake_redis):
    store = KpiStore(fake_redis)
    await store.write_health(
        "test_source", ok=False, last_success="2026-07-19T00:00:00Z", consecutive_failures=7
    )
    poller = ScriptedPoller(store, script=[])
    await poller.prime_from_existing_health()
    assert poller.consecutive_failures == 7
    assert poller.last_success == "2026-07-19T00:00:00Z"
