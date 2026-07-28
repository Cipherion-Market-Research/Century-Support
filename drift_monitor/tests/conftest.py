"""Test doubles: a fixture-backed fake GitHub client and a fake live-page
fetcher, plus paths to the local fixtures under tests/fixtures/. Kept
dependency-free (no aioresponses/vcrpy), same convention as
kpi_sync/tests/conftest.py and pubs_rag/tests/conftest.py.

No test in this package ever constructs a real aiohttp session against a
real host -- every network-shaped interface (GitHubClient, LiveFetcher)
is satisfied here by a double that reads bytes from local fixture files.
"""
from pathlib import Path
from typing import Optional

import pytest

from drift_monitor.config import Config
from drift_monitor.github_client import UntrackedRefError

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeGitHubClient:
    """Fixture-backed double for GitHubClient. `commit_log` maps a repo
    path to the list of commit dicts list_commits() should return for it
    (simulating "this path changed since last poll"); `file_contents` maps
    a repo path to the raw bytes fetch_raw() should return for it (i.e.
    "what's at HEAD of the tracked ref right now"). Both are set up by
    each test to script exactly the scenario under test -- no live network
    anywhere.
    """

    def __init__(self, commit_log: Optional[dict] = None, file_contents: Optional[dict] = None):
        self.commit_log = commit_log or {}
        self.file_contents = file_contents or {}
        self.list_commits_calls: list = []
        self.fetch_raw_calls: list = []

    async def list_commits(self, *, since=None, path=None, per_page=50):
        self.list_commits_calls.append({"since": since, "path": path})
        return self.commit_log.get(path, [])

    async def fetch_raw(self, path: str, ref: str = Config.TRACKED_REF) -> bytes:
        if ref != Config.TRACKED_REF:
            raise UntrackedRefError(f"refusing non-tracked ref {ref!r}")
        self.fetch_raw_calls.append({"path": path, "ref": ref})
        if path not in self.file_contents:
            raise KeyError(f"no fixture content registered for {path!r}")
        return self.file_contents[path]


class FakeLiveFetcher:
    """Fixture-backed double for parity_probe.LiveFetcher."""

    def __init__(self, pages_by_url: Optional[dict] = None):
        self.pages_by_url = pages_by_url or {}
        self.calls: list = []

    async def fetch_live_page(self, url: str) -> bytes:
        self.calls.append(url)
        if url not in self.pages_by_url:
            raise KeyError(f"no fixture content registered for {url!r}")
        return self.pages_by_url[url]


def read_fixture_bytes(*relative_parts: str) -> bytes:
    path = FIXTURES_DIR.joinpath(*relative_parts)
    return path.read_bytes()


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Point BASELINE_DIR/STATE_DIR/REPORTS_DIR at a scratch tmp_path for
    the duration of a test, so tests never read or write the real
    drift_monitor/baselines|state|reports directories."""
    baseline_dir = tmp_path / "baselines"
    state_dir = tmp_path / "state"
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr(Config, "BASELINE_DIR", str(baseline_dir))
    monkeypatch.setattr(Config, "STATE_DIR", str(state_dir))
    monkeypatch.setattr(Config, "REPORTS_DIR", str(reports_dir))
    return {"baseline_dir": baseline_dir, "state_dir": state_dir, "reports_dir": reports_dir}


@pytest.fixture
def facts_store():
    from facts_store.loader import FactsStore

    return FactsStore.load(FIXTURES_DIR / "facts_fixture.yaml")
