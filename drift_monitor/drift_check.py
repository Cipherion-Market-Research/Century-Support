"""Core detection pipeline: baseline text + current text -> a PageFinding
(or None if nothing changed). Pure/deterministic -- no I/O, no LLM. This
is the function both the scheduled poller and the test suite call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from drift_monitor.diff_engine import Hunk, compute_hunks, unified_diff_text
from drift_monitor.fact_matcher import HunkFinding, propose_new_value, reconcile_hunks
from drift_monitor.fingerprint import fingerprint_hunks
from facts_store.loader import FactsStore


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class ProposedFactEdit:
    fact_key: str
    current_value: Any
    proposed_value: Optional[str]  # None => ambiguous, flag for manual review
    source_url: str
    verified_on: str


@dataclass
class PageFinding:
    slug: str
    repo_path: str
    fingerprint: str
    unified_diff: str
    hunk_findings: list = field(default_factory=list)
    proposed_edits: list = field(default_factory=list)
    unmapped_hunk_count: int = 0
    detected_at: str = field(default_factory=utcnow_iso)
    # The full normalized current-page text this finding was computed
    # against, so a PR-mode caller can advance the baseline to it without
    # re-fetching (docs/BUILD_HANDOFF.md WP-7a: "every drift PR moves the
    # baseline snapshot with the fact -- else the same drift re-flags
    # forever"). Not part of the report/PR body itself.
    current_text: str = ""


def detect_page_drift(
    slug: str,
    repo_path: str,
    baseline_text: str,
    current_text: str,
    store: FactsStore,
) -> Optional[PageFinding]:
    """Returns None when `current_text` matches the baseline exactly
    (WP-7a acceptance line 2: unchanged fixture -> zero output)."""
    hunks = compute_hunks(baseline_text, current_text)
    if not hunks:
        return None

    hunk_findings: list[HunkFinding] = reconcile_hunks(hunks, store)
    fingerprint = fingerprint_hunks(slug, hunks)
    diff_text = unified_diff_text(baseline_text, current_text, fromfile=f"baseline:{slug}", tofile=f"current:{slug}")

    proposed_edits: list[ProposedFactEdit] = []
    unmapped_count = 0
    seen_keys = set()
    for hf in hunk_findings:
        if hf.unmapped:
            unmapped_count += 1
            continue
        for fact_key in hf.mapped_fact_keys:
            if fact_key in seen_keys:
                continue
            seen_keys.add(fact_key)
            fact = store.get(fact_key)
            if fact is None:
                continue
            new_value = propose_new_value(hf, fact_key, store)
            proposed_edits.append(
                ProposedFactEdit(
                    fact_key=fact_key,
                    current_value=fact.value,
                    proposed_value=new_value,
                    source_url=fact.source_url,
                    verified_on=str(fact.verified_on),
                )
            )

    return PageFinding(
        slug=slug,
        repo_path=repo_path,
        fingerprint=fingerprint,
        unified_diff=diff_text,
        hunk_findings=hunk_findings,
        proposed_edits=proposed_edits,
        unmapped_hunk_count=unmapped_count,
        current_text=current_text,
    )
