"""Orchestration-level tests for main.run_sitemap_parity_once: wiring the
sitemap fetch, the tracked-page manifest, and FindingsState dedup together,
plus the "unreachable sitemap never crashes the poller" acceptance line.

Same no-real-network convention as test_main.py: HttpSitemapFetcher is
monkeypatched to a fixture-backed FakeSitemapFetcher.
"""
from pathlib import Path

import aiohttp
import pytest

from drift_monitor import main as main_module
from drift_monitor.config import Config
from drift_monitor.page_manifest import WatchedPage
from drift_monitor.sitemap import SitemapFetchError
from drift_monitor.sitemap_parity import EXCLUDED_PRESENT, NEW_PAGE, REMOVED_PAGE
from drift_monitor.tests.conftest import FakeSitemapFetcher, read_fixture_bytes

SITEMAP_XML = read_fixture_bytes("sitemap.xml")  # 11 <loc> entries; includes insights-and-publications

# Every fixture sitemap.xml slug EXCEPT insights-and-publications (that
# one is EXCLUDED_SLUGS -- tracking it would be wrong), plus one stale
# slug ("retired-page") that is absent from the fixture sitemap and isn't
# a known-noindex page either. KNOWN_NOINDEX_SLUGS are deliberately left
# untracked. Together this exercises all three finding kinds at once:
# new (the six noindex pages), removed (retired-page), and
# excluded_present (insights-and-publications, seen in the sitemap).
TRACKED_PAGES = [
    WatchedPage(slug=slug, repo_path=f"src/{slug}.html", source_url=f"https://ciphex.io/{slug}")
    for slug in ("index", "about", "ciphex-token", "faq", "team", "roadmap", "careers", "press", "partners", "privacy-policy")
] + [
    WatchedPage(slug="retired-page", repo_path="src/retired-page.html", source_url="https://ciphex.io/retired-page"),
]


def _wire(monkeypatch):
    monkeypatch.setattr(main_module, "load_watched_pages", lambda: TRACKED_PAGES)
    fake_fetcher = FakeSitemapFetcher({Config.SITEMAP_URL: SITEMAP_XML})
    monkeypatch.setattr(main_module, "HttpSitemapFetcher", lambda session: fake_fetcher)
    return fake_fetcher


@pytest.mark.asyncio
async def test_run_sitemap_parity_once_emits_all_three_finding_kinds(isolated_dirs, monkeypatch):
    _wire(monkeypatch)

    async with aiohttp.ClientSession() as session:
        findings = await main_module.run_sitemap_parity_once(session)

    kinds = {f.kind for f in findings}
    assert kinds == {NEW_PAGE, REMOVED_PAGE, EXCLUDED_PRESENT}

    new_slugs = {f.slug for f in findings if f.kind == NEW_PAGE}
    assert new_slugs == set(Config.KNOWN_NOINDEX_SLUGS)

    removed_slugs = {f.slug for f in findings if f.kind == REMOVED_PAGE}
    assert removed_slugs == {"retired-page"}

    excluded_slugs = {f.slug for f in findings if f.kind == EXCLUDED_PRESENT}
    assert excluded_slugs == {"insights-and-publications"}

    # A report was written for this cycle's findings.
    written = list(Path(Config.REPORTS_DIR).glob("*sitemap-parity*.md"))
    assert len(written) == 1


@pytest.mark.asyncio
async def test_run_sitemap_parity_once_dedupes_repeat_findings(isolated_dirs, monkeypatch):
    _wire(monkeypatch)

    async with aiohttp.ClientSession() as session:
        first = await main_module.run_sitemap_parity_once(session)
    assert len(first) > 0

    async with aiohttp.ClientSession() as session2:
        second = await main_module.run_sitemap_parity_once(session2)

    assert second == []  # same structural findings, already recorded -> suppressed


@pytest.mark.asyncio
async def test_run_sitemap_parity_once_skips_gracefully_when_sitemap_unreachable(isolated_dirs, monkeypatch):
    monkeypatch.setattr(main_module, "load_watched_pages", lambda: TRACKED_PAGES)
    failing_fetcher = FakeSitemapFetcher(error=SitemapFetchError("connection refused"))
    monkeypatch.setattr(main_module, "HttpSitemapFetcher", lambda session: failing_fetcher)

    async with aiohttp.ClientSession() as session:
        findings = await main_module.run_sitemap_parity_once(session)  # must not raise

    assert findings == []
    assert list(Path(Config.REPORTS_DIR).glob("*sitemap-parity*.md")) == []
