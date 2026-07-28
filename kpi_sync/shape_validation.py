"""Per-source payload shape validation (WP-7c serving-safety hardening).

Each HTTP-JSON poller declares the top-level keys it expects in its
upstream payload (see the `*_EXPECTED_KEYS` tuples in config.py, kept beside
each poller's own config block). On a *successful* fetch whose payload is
missing one or more of those keys -- an upstream rename/removal, not a
network failure -- the poller is marked `degraded` rather than silently
serving (or dropping) fields as if nothing changed:

  - a `kpi:<source>:__shape` status envelope is written through the normal
    C3 envelope path (KpiStore.write_kpi -- same KpiEnvelope shape as every
    other metric, not a new schema) recording which keys were missing;
  - the poll cycle is flagged (BasePoller.mark_degraded /
    report_shape_degraded) so `kpi:<source>:__health` comes out
    `{"ok": false, ..., "reason": "shape_change"}` instead of a plain
    success -- see pollers/base.py.

Gated by Config.SHAPE_VALIDATION_ENABLED (env KPI_SYNC_SHAPE_VALIDATION_ENABLED,
default true) so the whole check is one flag away from being disabled if it
ever misfires against a legitimate upstream change -- mirrors the
KPI_SYNC_ABACUS_ENABLED on/off pattern in config.py.

Only dict-shaped payloads are checked here. Sources whose payload is a list
(abacus_index) or that have no single upstream JSON body to speak of
(the on-chain pollers, which read individual contract fields) declare no
expected-shape tuple and are out of scope for this check.
"""
from typing import Iterable, List


def missing_keys(data, expected_keys: Iterable[str]) -> List[str]:
    """Return the expected top-level keys absent from `data`, in
    declaration order. A non-dict payload is reported as entirely missing
    (callers with list-shaped payloads should not use this helper)."""
    if not isinstance(data, dict):
        return list(expected_keys)
    return [k for k in expected_keys if k not in data]
