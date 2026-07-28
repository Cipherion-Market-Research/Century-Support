import pytest

from drift_monitor.page_manifest import WatchedPage
from drift_monitor.parity_probe import check_page_parity, render_parity_report_markdown, run_parity_probe
from drift_monitor.tests.conftest import FakeGitHubClient, FakeLiveFetcher, read_fixture_bytes

PAGE = WatchedPage(slug="sample-page", repo_path="src/sample-page.html", source_url="https://ciphex.io/sample-page")


@pytest.mark.asyncio
async def test_check_page_parity_matches_when_identical():
    html = read_fixture_bytes("repo_checkout", "src", "sample-page.html")
    live_fetcher = FakeLiveFetcher({PAGE.source_url: html})
    github_client = FakeGitHubClient(file_contents={PAGE.repo_path: html})

    result = await check_page_parity(PAGE.slug, PAGE.repo_path, PAGE.source_url, live_fetcher, github_client)

    assert result.matches is True
    assert result.diff_text == ""


@pytest.mark.asyncio
async def test_check_page_parity_flags_mismatch():
    repo_html = read_fixture_bytes("repo_checkout", "src", "sample-page.html")
    live_html = read_fixture_bytes("repo_checkout", "src", "sample-page-edited.html")
    live_fetcher = FakeLiveFetcher({PAGE.source_url: live_html})
    github_client = FakeGitHubClient(file_contents={PAGE.repo_path: repo_html})

    result = await check_page_parity(PAGE.slug, PAGE.repo_path, PAGE.source_url, live_fetcher, github_client)

    assert result.matches is False
    assert "help@ciphex.io" in result.diff_text


@pytest.mark.asyncio
async def test_run_parity_probe_covers_all_sentinel_pages():
    html = read_fixture_bytes("repo_checkout", "src", "sample-page.html")
    live_fetcher = FakeLiveFetcher({PAGE.source_url: html})
    github_client = FakeGitHubClient(file_contents={PAGE.repo_path: html})

    results = await run_parity_probe([PAGE], live_fetcher, github_client)

    assert len(results) == 1
    assert results[0].matches is True


def test_render_parity_report_includes_mismatch_diff():
    from drift_monitor.parity_probe import ParityResult

    results = [
        ParityResult(slug="sample-page", live_url="https://ciphex.io/sample-page", repo_path="src/sample-page.html", matches=False, diff_text="-old\n+new")
    ]
    md = render_parity_report_markdown(results)
    assert "MISMATCH" in md
    assert "-old" in md and "+new" in md
