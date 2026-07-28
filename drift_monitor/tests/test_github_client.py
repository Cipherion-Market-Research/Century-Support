"""Every commits-API query and every raw-content fetch this service can
ever make is pinned to Config.TRACKED_REF ("main") -- these tests assert
that at the URL/parameter level so a future change can't quietly widen
the surface to other branches (non-main content must never enter a drift
report or a proposed facts.yaml edit, even as evidence)."""
import pytest

from drift_monitor.config import Config
from drift_monitor.github_client import GitHubClient, UntrackedRefError


def test_tracked_ref_is_main():
    assert Config.TRACKED_REF == "main"


def test_raw_url_is_pinned_to_tracked_ref():
    url = GitHubClient.raw_url("acme", "site", "src/index.html")
    assert url == f"{Config.GITHUB_RAW_BASE_URL}/acme/site/main/src/index.html"


@pytest.mark.asyncio
async def test_fetch_raw_rejects_non_tracked_ref():
    client = GitHubClient(session=None)  # never reaches the network -- rejected before any request
    with pytest.raises(UntrackedRefError):
        await client.fetch_raw("src/index.html", ref="some-feature-branch")


@pytest.mark.asyncio
async def test_list_commits_always_queries_tracked_ref():
    captured = {}

    class FakeResp:
        status = 200

        async def json(self, content_type=None):
            return []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class FakeSession:
        def get(self, url, params=None, headers=None, timeout=None):
            captured["url"] = url
            captured["params"] = params
            return FakeResp()

    client = GitHubClient(session=FakeSession(), owner="acme", repo="site")
    await client.list_commits(path="src/index.html")

    assert captured["params"]["sha"] == "main"
    assert captured["url"].endswith("/repos/acme/site/commits")
