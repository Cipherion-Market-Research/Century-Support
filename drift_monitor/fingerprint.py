"""Fingerprint a page's changed-hunk set so the same drift, re-detected on
a later poll, is recognized as the same finding rather than a new one.

sha256 of a canonical (order-stable, whitespace-normalized) string built
from the hunk opcodes -- deterministic given the same old/new text pair,
which is all `compute_hunks` needs to reproduce the same hunk list.
"""
from __future__ import annotations

import hashlib

from drift_monitor.diff_engine import Hunk


def fingerprint_hunks(slug: str, hunks: list) -> str:
    parts = [f"slug={slug}"]
    for h in hunks:
        parts.append(f"{h.op}|OLD:{h.old_text}|NEW:{h.new_text}")
    canonical = "\n---\n".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
