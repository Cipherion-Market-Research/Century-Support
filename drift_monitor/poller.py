"""One content-drift poll cycle: commits-API check -> conditional raw
fetch -> diff -> fact reconciliation -> dedup -> shadow report or PR
preview, wired together.

`github_client` is injected everywhere (never constructed here), so this
module runs identically against the real GitHubClient or a fixture-backed
test double -- see tests/test_poller.py.
"""
from __future__ import annotations

from typing import Optional

from drift_monitor.baseline import BaselineManifest
from drift_monitor.config import Config
from drift_monitor.drift_check import PageFinding, detect_page_drift
from drift_monitor.html_normalize import extract_body_text
from drift_monitor.logging_setup import get_logger
from drift_monitor.page_manifest import WatchedPage
from drift_monitor.state import FindingsState, PollState, utcnow_iso
from facts_store.loader import FactsStore

logger = get_logger("drift_monitor.poller")


async def run_poll_cycle(
    pages: list,
    github_client,
    store: FactsStore,
    baseline: BaselineManifest,
    findings_state: FindingsState,
    poll_state: Optional[PollState] = None,
) -> list:
    """Returns the list of NEW (non-duplicate) PageFinding objects from
    this cycle. Callers (main.py) decide what to do with them (shadow
    report vs. PR preview) -- this function has no side effect beyond the
    GitHub reads it performs through the injected client."""
    since = poll_state.get_last_checked() if poll_state else None
    new_findings: list[PageFinding] = []

    for page in pages:
        try:
            commits = await github_client.list_commits(since=since, path=page.repo_path)
        except Exception:
            logger.error(
                "commits-API check failed", extra={"event": "commits_check_failed", "slug": page.slug, "path": page.repo_path},
                exc_info=True,
            )
            continue

        if not commits:
            continue

        try:
            current_bytes = await github_client.fetch_raw(page.repo_path, Config.TRACKED_REF)
        except Exception:
            logger.error(
                "raw fetch failed", extra={"event": "raw_fetch_failed", "slug": page.slug, "path": page.repo_path},
                exc_info=True,
            )
            continue

        current_text = extract_body_text(current_bytes.decode("utf-8"))
        baseline_text = baseline.get_text(page.slug) or ""

        finding = detect_page_drift(page.slug, page.repo_path, baseline_text, current_text, store)
        if finding is None:
            logger.info(
                "commits touched path but normalized text is unchanged",
                extra={"event": "no_effective_drift", "slug": page.slug},
            )
            continue

        if findings_state.seen(page.slug, finding.fingerprint):
            logger.info(
                "duplicate finding suppressed",
                extra={"event": "duplicate_suppressed", "slug": page.slug, "fingerprint": finding.fingerprint},
            )
            continue

        logger.info(
            "new drift finding",
            extra={"event": "new_finding", "slug": page.slug, "fingerprint": finding.fingerprint},
        )
        new_findings.append(finding)

    if poll_state:
        poll_state.set_last_checked(utcnow_iso())

    return new_findings
