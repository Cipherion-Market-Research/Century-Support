"""End-to-end poll-cycle tests against fixture data only (no live
network, no LLM). Covers acceptance lines 1-3 through the full
run_poll_cycle path (commits-API check -> raw fetch -> diff -> fact
reconciliation -> dedup)."""
import pytest

from drift_monitor.baseline import BaselineManifest
from drift_monitor.page_manifest import WatchedPage
from drift_monitor.poller import run_poll_cycle
from drift_monitor.state import FindingsState, PollState
from drift_monitor.tests.conftest import FakeGitHubClient, read_fixture_bytes

PAGE = WatchedPage(slug="sample-page", repo_path="src/sample-page.html", source_url="https://ciphex.io/sample-page")


def _seeded_baseline(isolated_dirs) -> BaselineManifest:
    baseline_html = read_fixture_bytes("repo_checkout", "src", "sample-page.html")
    manifest = BaselineManifest()
    manifest.load()
    from drift_monitor.html_normalize import extract_body_text

    manifest.set_page(PAGE.slug, PAGE.repo_path, extract_body_text(baseline_html.decode("utf-8")), seeded_from="test")
    manifest.save()
    return manifest


@pytest.mark.asyncio
async def test_poll_cycle_detects_seeded_edit_with_one_commit(isolated_dirs, facts_store):
    baseline = _seeded_baseline(isolated_dirs)
    edited_html = read_fixture_bytes("repo_checkout", "src", "sample-page-edited.html")

    github_client = FakeGitHubClient(
        commit_log={PAGE.repo_path: [{"sha": "c1"}]},
        file_contents={PAGE.repo_path: edited_html},
    )
    findings_state = FindingsState().load()
    poll_state = PollState().load()

    findings = await run_poll_cycle([PAGE], github_client, facts_store, baseline, findings_state, poll_state)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.slug == "sample-page"
    matched = [e for e in finding.proposed_edits if e.fact_key == "identity.support_email"]
    assert matched and matched[0].proposed_value == "help@ciphex.io"
    # Poll cursor advances even though this is the fixture path (no live network).
    assert poll_state.get_last_checked() is not None


@pytest.mark.asyncio
async def test_poll_cycle_skips_pages_with_no_recent_commits(isolated_dirs, facts_store):
    baseline = _seeded_baseline(isolated_dirs)
    github_client = FakeGitHubClient(commit_log={}, file_contents={})  # no commits registered for this path
    findings_state = FindingsState().load()

    findings = await run_poll_cycle([PAGE], github_client, facts_store, baseline, findings_state)

    assert findings == []
    # fetch_raw must never be called if the commits check found nothing.
    assert github_client.fetch_raw_calls == []


@pytest.mark.asyncio
async def test_poll_cycle_same_seeded_drift_run_twice_yields_one_finding_not_two(isolated_dirs, facts_store):
    """WP-7a acceptance line 3."""
    baseline = _seeded_baseline(isolated_dirs)
    edited_html = read_fixture_bytes("repo_checkout", "src", "sample-page-edited.html")
    github_client = FakeGitHubClient(
        commit_log={PAGE.repo_path: [{"sha": "c1"}]},
        file_contents={PAGE.repo_path: edited_html},
    )

    findings_state = FindingsState().load()

    first_run = await run_poll_cycle([PAGE], github_client, facts_store, baseline, findings_state)
    assert len(first_run) == 1
    for f in first_run:
        findings_state.record(f.slug, f.fingerprint, report_path="report-1.md")
    findings_state.save()

    # Second poll cycle sees the SAME drift again (nothing changed on the
    # repo side between polls) -- must be suppressed as a duplicate.
    findings_state_reloaded = FindingsState().load()
    second_run = await run_poll_cycle(
        [PAGE], github_client, facts_store, baseline, findings_state_reloaded
    )

    assert second_run == []  # duplicate suppressed, not a second finding
