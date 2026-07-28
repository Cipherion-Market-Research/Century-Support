"""Orchestration-level tests for main.run_content_poll_once, covering the
WP-7a acceptance lines that only show up when the whole pipeline is wired
together: PR mode never fires with DRIFT_OPEN_PRS off (default), and when
it IS on, exactly one consolidated PR preview is prepared and the
baseline advances. No real aiohttp request is ever made -- GitHubClient
is monkeypatched to a fixture-backed double, and the real
GhCliPrCreator.create_pr (the only spot that could shell out to `gh`) is
monkeypatched to fail the test if it's ever actually invoked.
"""
from pathlib import Path

import aiohttp
import pytest

from drift_monitor import main as main_module
from drift_monitor.baseline import BaselineManifest
from drift_monitor.config import Config
from drift_monitor.gh_pr import GhCliPrCreator
from drift_monitor.html_normalize import extract_body_text
from drift_monitor.page_manifest import WatchedPage
from drift_monitor.tests.conftest import FIXTURES_DIR, FakeGitHubClient, read_fixture_bytes

PAGE = WatchedPage(slug="sample-page", repo_path="src/sample-page.html", source_url="https://ciphex.io/sample-page")


def _seed_baseline():
    baseline_html = read_fixture_bytes("repo_checkout", "src", "sample-page.html")
    manifest = BaselineManifest()
    manifest.load()
    manifest.set_page(PAGE.slug, PAGE.repo_path, extract_body_text(baseline_html.decode("utf-8")), seeded_from="test")
    manifest.save()


def _wire_common(monkeypatch, isolated_dirs):
    monkeypatch.setattr(Config, "FACTS_YAML_PATH", str(FIXTURES_DIR / "facts_fixture.yaml"))
    monkeypatch.setattr(main_module, "load_watched_pages", lambda: [PAGE])
    edited_html = read_fixture_bytes("repo_checkout", "src", "sample-page-edited.html")
    fake_client = FakeGitHubClient(
        commit_log={PAGE.repo_path: [{"sha": "c1"}]}, file_contents={PAGE.repo_path: edited_html}
    )
    monkeypatch.setattr(main_module, "GitHubClient", lambda session: fake_client)
    _seed_baseline()
    return fake_client


@pytest.mark.asyncio
async def test_pr_mode_never_fires_when_flag_off(isolated_dirs, monkeypatch):
    monkeypatch.setattr(Config, "OPEN_PRS", False)
    _wire_common(monkeypatch, isolated_dirs)

    def _fail_if_called(self, preview):
        raise AssertionError("GhCliPrCreator.create_pr must never be called when DRIFT_OPEN_PRS is false")

    monkeypatch.setattr(GhCliPrCreator, "create_pr", _fail_if_called)

    async with aiohttp.ClientSession() as session:
        findings = await main_module.run_content_poll_once(session)

    assert len(findings) == 1
    written = list(Path(Config.REPORTS_DIR).glob("*.md"))
    assert len(written) == 1  # shadow report, not a PR


@pytest.mark.asyncio
async def test_pr_mode_prepares_one_consolidated_pr_and_advances_baseline(isolated_dirs, monkeypatch):
    monkeypatch.setattr(Config, "OPEN_PRS", True)
    _wire_common(monkeypatch, isolated_dirs)

    captured_previews = []

    def _capture(self, preview):
        captured_previews.append(preview)
        return {"created": False, "reason": "test double -- no real gh invocation"}

    monkeypatch.setattr(GhCliPrCreator, "create_pr", _capture)

    async with aiohttp.ClientSession() as session:
        findings = await main_module.run_content_poll_once(session)

    assert len(findings) == 1
    assert len(captured_previews) == 1
    preview = captured_previews[0]
    assert "identity.support_email" in preview.body
    assert "help@ciphex.io" in preview.body

    # No shadow report written in PR mode.
    assert list(Path(Config.REPORTS_DIR).glob("*.md")) == []

    # Baseline advanced to the new content (WP-7a: "every drift PR moves
    # the baseline snapshot with the fact").
    reloaded = BaselineManifest().load()
    assert "help@ciphex.io" in reloaded.get_text(PAGE.slug)

    # Re-running the same cycle now finds no drift (baseline caught up).
    async with aiohttp.ClientSession() as session2:
        findings_again = await main_module.run_content_poll_once(session2)
    assert findings_again == []
