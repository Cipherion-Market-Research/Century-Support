"""kpi_sync -> century_core KPI envelope round-trip test (golive-p2, gap #2).

Today nothing tests the real seam between kpi_sync's writer and
century_core's reader: kpi_sync/tests/test_envelope.py exercises KpiStore
against its own private FakeRedis, and century_core/tests/test_kpi_reader.py
exercises KpiReader against a *different* private FakeRedis
(century_core/tests/conftest.py's `seed_kpi` helper hand-builds the JSON
envelope rather than going through kpi_sync's real writer). A key-builder
or field rename on either side could pass both suites independently while
breaking the real integration.

This test writes with the REAL kpi_sync.envelope.KpiStore and reads with
the REAL century_core.kpi_reader.KpiReader, against one minimal dict-backed
fake Redis defined here (not either suite's private fake -- those aren't
importable across suites, see conftest.py's own docstring). The fake only
implements what these two real async clients actually call: `get` (both
sides) and `set` with an `ex` kwarg (KpiStore.write_kpi/write_health) --
enumerated by reading kpi_sync/envelope.py and century_core/kpi_reader.py
directly, not guessed.

Key point: KpiReader already reuses KpiStore.kpi_key/health_key directly
(see kpi_reader.py's own docstring -- "reuses its public static
key-builder methods... for DRY-ness"), so this test does not re-derive
keys itself anywhere; both sides go through the one real key builder,
exactly as they do in production.
"""
import pytest

from century_core.config import Config
from century_core.kpi_reader import BlockedKpiSourceError, KpiReader
from kpi_sync.envelope import KpiStore


class FakeRedis:
    """Dict-backed fake satisfying exactly the methods the real KpiStore
    (write side) and KpiReader (read side) call: async get(key) and async
    set(key, value, ex=None). No expire/ttl/mget -- neither real client
    calls them."""

    def __init__(self):
        self._data: dict[str, str] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value: str, ex=None) -> None:
        self._data[key] = value


@pytest.fixture
def redis():
    return FakeRedis()


# ───────────────────────── claim_api-style envelope round trip ─────────────────────────


async def test_claim_api_envelope_written_by_kpi_sync_is_read_by_century_core(redis):
    writer = KpiStore(redis)
    reader = KpiReader(redis)

    await writer.write_kpi(
        "claim_api",
        "cipherions",
        62,
        source_url="https://claim.ciphex.io/api/presale",
        as_of="2026-08-15T12:00:00Z",
        ttl_s=3600,
        stale_after_s=1800,
    )

    reading = await reader.read("claim_api", "cipherions")
    assert reading is not None
    assert reading.source == "claim_api"
    assert reading.metric == "cipherions"
    assert reading.value == 62
    assert reading.source_url == "https://claim.ciphex.io/api/presale"
    assert reading.as_of == "2026-08-15T12:00:00Z"
    assert reading.fetched_at is not None
    assert reading.stale is False


async def test_claim_api_envelope_with_dict_value_round_trips_intact(redis):
    # write_flat_metrics/write_kpi both allow structured values (e.g. the
    # {"ui": ..., "raw": ...} shape claim_api actually uses upstream) --
    # confirm the reader hands the structure back unmangled, not just a
    # scalar.
    writer = KpiStore(redis)
    reader = KpiReader(redis)

    await writer.write_kpi(
        "claim_api",
        "price",
        {"ui": "$0.26", "raw": 0.26},
        source_url="https://claim.ciphex.io/api/presale",
        as_of=None,
        ttl_s=3600,
        stale_after_s=1800,
    )

    reading = await reader.read("claim_api", "price")
    assert reading.value == {"ui": "$0.26", "raw": 0.26}
    assert reading.as_of is None


# ───────────────────────── staleness semantics ─────────────────────────


async def test_freshly_written_envelope_is_not_stale(redis):
    writer = KpiStore(redis)
    reader = KpiReader(redis)

    await writer.write_kpi(
        "claim_api",
        "cipherions",
        62,
        source_url="https://claim.ciphex.io/api/presale",
        as_of=None,
        ttl_s=3600,
        stale_after_s=1800,
    )

    reading = await reader.read("claim_api", "cipherions")
    assert reading.stale is False


async def test_envelope_older_than_stale_after_s_is_flagged_stale_by_reader(redis, monkeypatch):
    # KpiStore.write_kpi always stamps fetched_at = utcnow_iso() itself (no
    # override parameter -- by design, see envelope.py) so the only way to
    # exercise the REAL writer's stale-write path is to fake its clock, not
    # to hand-build the JSON envelope. C3 rule under test (kpi_reader.py):
    # "now - fetched_at > stale_after_s is STALE".
    old_fetched_at = "2020-01-01T00:00:00Z"
    monkeypatch.setattr("kpi_sync.envelope.utcnow_iso", lambda: old_fetched_at)

    writer = KpiStore(redis)
    reader = KpiReader(redis)

    await writer.write_kpi(
        "claim_api",
        "cipherions",
        62,
        source_url="https://claim.ciphex.io/api/presale",
        as_of=None,
        ttl_s=999999999,
        stale_after_s=1800,
    )

    reading = await reader.read("claim_api", "cipherions")
    assert reading.fetched_at == old_fetched_at
    assert reading.stale is True


# ───────────────────────── health sidecar round trip ─────────────────────────


async def test_health_written_by_kpi_sync_is_read_by_century_core(redis):
    writer = KpiStore(redis)
    reader = KpiReader(redis)

    await writer.write_health(
        "claim_api",
        ok=True,
        last_success="2026-08-15T12:00:00Z",
        consecutive_failures=0,
    )

    health = await reader.read_health("claim_api")
    assert health is not None
    assert health["ok"] is True
    assert health["last_success"] == "2026-08-15T12:00:00Z"
    assert health["consecutive_failures"] == 0


async def test_health_failure_state_round_trips_with_reason(redis):
    writer = KpiStore(redis)
    reader = KpiReader(redis)

    await writer.write_health(
        "claim_api",
        ok=False,
        last_success="2026-08-14T00:00:00Z",
        consecutive_failures=3,
        reason="shape_change",
    )

    health = await reader.read_health("claim_api")
    assert health["ok"] is False
    assert health["consecutive_failures"] == 3
    assert health["reason"] == "shape_change"


# ───────────────────────── negative: blocked sources ─────────────────────────


@pytest.mark.parametrize("blocked_source", sorted(Config.BLOCKED_KPI_SOURCES))
async def test_blocked_source_written_by_kpi_sync_is_refused_by_reader(redis, blocked_source):
    # onchain_base / abacus_index (owner ruling, config.py) are valid C3
    # sources kpi_sync legitimately writes -- the block is a century_core
    # read-side policy, not something kpi_sync itself withholds. Confirm
    # KpiReader actually enforces it against a REAL envelope this source
    # wrote, not a synthetic one.
    writer = KpiStore(redis)
    reader = KpiReader(redis)

    await writer.write_kpi(
        blocked_source,
        "latest",
        123.45,
        source_url="https://example.ciphex.io/feed",
        as_of=None,
        ttl_s=3600,
        stale_after_s=1800,
    )

    with pytest.raises(BlockedKpiSourceError):
        await reader.read(blocked_source, "latest")


@pytest.mark.parametrize("blocked_source", sorted(Config.BLOCKED_KPI_SOURCES))
async def test_blocked_source_health_is_also_refused_by_reader(redis, blocked_source):
    writer = KpiStore(redis)
    reader = KpiReader(redis)

    await writer.write_health(blocked_source, ok=True, last_success="2026-08-15T00:00:00Z", consecutive_failures=0)

    with pytest.raises(BlockedKpiSourceError):
        await reader.read_health(blocked_source)
