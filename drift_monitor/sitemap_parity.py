"""Sitemap-parity check: is the page universe this service tracks in sync
with what the live sitemap advertises?

sitemap.xml is a DISCOVERY signal, not the tracked-page scope itself:

  - Six public pages are deliberately noindexed for SEO and never appear
    in the sitemap, but ARE part of the bot's knowledge scope
    (Config.KNOWN_NOINDEX_SLUGS).
  - insights-and-publications IS in the sitemap but is excluded from bot
    knowledge per the 2026-08-18 Bot Parameter Requirements
    (Config.EXCLUDED_SLUGS).

So the scope this service is expected to track is:

    expected_tracked = (sitemap_slugs | KNOWN_NOINDEX_SLUGS) - EXCLUDED_SLUGS

This module only ever proposes findings for a human to act on --
`sitemap_new_page` (in expected scope, not tracked -- harvest/facts may
need a refresh), `sitemap_removed_page` (tracked, no longer in expected
scope), and `sitemap_excluded_present` (informational: an excluded slug
was seen in the sitemap, which is expected, logged once for visibility).
It never edits data/kb_source/inventory.json, the page manifest, or the
baseline itself -- same propose-only/HITL posture as drift_check.py (see
docs/CONTRACTS.md C4).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from drift_monitor.config import Config
from drift_monitor.state import utcnow_iso

NEW_PAGE = "sitemap_new_page"
REMOVED_PAGE = "sitemap_removed_page"
EXCLUDED_PRESENT = "sitemap_excluded_present"


@dataclass
class SitemapFinding:
    kind: str  # one of NEW_PAGE / REMOVED_PAGE / EXCLUDED_PRESENT
    slug: str
    detail: str
    detected_at: str = field(default_factory=utcnow_iso)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        # Deterministic given (kind, slug) alone -- unlike content-drift
        # findings, a sitemap finding isn't about *what* changed in a
        # page's text, only about its presence/absence/exclusion, so the
        # identity of the finding is fully captured by kind+slug. This is
        # what lets FindingsState dedup the same structural finding across
        # repeated poll cycles (see main.run_sitemap_parity_once).
        self.fingerprint = hashlib.sha256(f"{self.kind}:{self.slug}".encode("utf-8")).hexdigest()


def compute_expected_tracked(sitemap_slugs) -> set:
    """expected_tracked = (sitemap ∪ known-noindex) − excluded."""
    return (set(sitemap_slugs) | set(Config.KNOWN_NOINDEX_SLUGS)) - set(Config.EXCLUDED_SLUGS)


def check_sitemap_parity(sitemap_slugs, tracked_slugs) -> list:
    """Pure set comparison -- no I/O. `tracked_slugs` is whatever the
    caller derives as "pages this service currently tracks" (main.py uses
    the watched-page manifest, page_manifest.load_watched_pages()).

    Returns SitemapFinding objects in a stable, sorted (kind, then slug)
    order for deterministic tests/logs.
    """
    sitemap_set = set(sitemap_slugs)
    tracked_set = set(tracked_slugs)
    expected = compute_expected_tracked(sitemap_set)

    findings: list[SitemapFinding] = []

    for slug in sorted(expected - tracked_set):
        findings.append(
            SitemapFinding(
                kind=NEW_PAGE,
                slug=slug,
                detail=(
                    f"'{slug}' is in scope (sitemap and/or known-noindex pages) but is not in "
                    "the tracked page manifest -- harvest/facts may need a refresh."
                ),
            )
        )

    for slug in sorted(tracked_set - expected):
        findings.append(
            SitemapFinding(
                kind=REMOVED_PAGE,
                slug=slug,
                detail=(
                    f"'{slug}' is tracked but no longer in scope (absent from the sitemap and not "
                    "a known-noindex page, or newly excluded) -- confirm whether it should be retired."
                ),
            )
        )

    for slug in sorted(sitemap_set & set(Config.EXCLUDED_SLUGS)):
        findings.append(
            SitemapFinding(
                kind=EXCLUDED_PRESENT,
                slug=slug,
                detail=(
                    f"'{slug}' is present in sitemap.xml but excluded from bot knowledge scope "
                    "per the 2026-08-18 Bot Parameter Requirements -- expected, logged for visibility."
                ),
            )
        )

    return findings


def render_sitemap_parity_report_markdown(findings) -> str:
    lines = ["# Sitemap-parity findings", "", f"Checked at: {utcnow_iso()}", ""]
    for f in findings:
        lines.append(f"## {f.kind}: {f.slug}")
        lines.append(f"- Fingerprint: `{f.fingerprint}`")
        lines.append(f"- Detected at: {f.detected_at}")
        lines.append(f"- {f.detail}")
        lines.append("")
    lines.append(
        "---\n_This report is informational only (advisory, shadow mode). It never mutates "
        "data/kb_source/inventory.json, the page manifest, or the baseline; see docs/CONTRACTS.md C4._"
    )
    return "\n".join(lines)


def write_sitemap_parity_report(findings, reports_dir: Optional[str] = None) -> Path:
    directory = Path(reports_dir if reports_dir is not None else Config.REPORTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    ts = utcnow_iso().replace(":", "").replace("-", "")
    path = directory / f"{ts}-sitemap-parity.md"
    path.write_text(render_sitemap_parity_report_markdown(findings), encoding="utf-8")
    return path
