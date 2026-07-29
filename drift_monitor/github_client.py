"""GitHub read access for the drift monitor: commits API polling (for
"has anything under src/*.html changed since last check") + raw-content
fetch (for "what does that file say now"), pinned to Config.TRACKED_REF.

Follows pubs_rag/webhook.py's fetch_raw_file style (build the raw URL from
owner/repo/ref/path, GET, raise_for_status, read the body) without
modifying that module -- this is a separate service with its own copy.

Every method here takes an explicit `ref` only to assert it against
Config.TRACKED_REF; there is no way to make a request against any other
ref through this client. This is deliberate (see config.py's TRACKED_REF
docstring): non-main content must never enter a drift report or a
proposed facts.yaml edit, even as evidence.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

from drift_monitor.config import Config
from drift_monitor.retry import retry_async

logger = logging.getLogger(__name__)


class GitHubClientError(Exception):
    pass


class UntrackedRefError(GitHubClientError):
    """Raised if any code path tries to read a ref other than Config.TRACKED_REF."""


class GitHubClient:
    """Thin async wrapper over the GitHub REST API, scoped to one repo.

    Real network implementation. Tests inject a fixture-backed double
    with the same method signatures (see tests/conftest.py) -- this class
    is never imported by a test that wants live network.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        owner: str = Config.GITHUB_REPO_OWNER,
        repo: str = Config.GITHUB_REPO_NAME,
    ):
        self.session = session
        self.owner = owner
        self.repo = repo

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if Config.GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {Config.GITHUB_TOKEN}"
        return headers

    async def list_commits(
        self, *, since: Optional[str] = None, path: Optional[str] = None, per_page: int = 50
    ) -> list[dict]:
        """GET /repos/{owner}/{repo}/commits?sha=main[&since=...][&path=...]

        Always queries Config.TRACKED_REF ("main") -- there is no
        parameter to override that. Returns the raw list of commit
        objects (each has at least "sha" and "commit.committer.date").
        """
        params = {"sha": Config.TRACKED_REF, "per_page": str(per_page)}
        if since:
            params["since"] = since
        if path:
            params["path"] = path
        url = f"{Config.GITHUB_API_BASE_URL}/repos/{self.owner}/{self.repo}/commits"

        async def _do() -> Any:
            timeout = aiohttp.ClientTimeout(total=Config.HTTP_TIMEOUT_S)
            async with self.session.get(
                url, params=params, headers=self._headers(), timeout=timeout
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise GitHubClientError(f"commits API {resp.status} from {url}: {body[:300]}")
                return await resp.json(content_type=None)

        return await retry_async(_do)

    async def fetch_raw(self, path: str, ref: str = Config.TRACKED_REF) -> bytes:
        """GET raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}

        `ref` defaults to (and must equal) Config.TRACKED_REF. Any other
        value raises UntrackedRefError before a request is ever made.
        """
        if ref != Config.TRACKED_REF:
            raise UntrackedRefError(
                f"refusing to fetch {path!r} at ref {ref!r} -- this service only ever "
                f"reads Config.TRACKED_REF ({Config.TRACKED_REF!r})"
            )
        url = f"{Config.GITHUB_RAW_BASE_URL}/{self.owner}/{self.repo}/{ref}/{path}"

        async def _do() -> bytes:
            timeout = aiohttp.ClientTimeout(total=Config.HTTP_TIMEOUT_S)
            headers = {}
            if Config.GITHUB_TOKEN:
                headers["Authorization"] = f"Bearer {Config.GITHUB_TOKEN}"
            async with self.session.get(url, timeout=timeout, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise GitHubClientError(f"raw fetch {resp.status} from {url}: {body[:300]}")
                return await resp.read()

        return await retry_async(_do)

    @staticmethod
    def raw_url(owner: str, repo: str, path: str, ref: str = Config.TRACKED_REF) -> str:
        """Pure URL-builder (no I/O) used by tests to assert every raw URL
        this service could ever construct is pinned to Config.TRACKED_REF."""
        return f"{Config.GITHUB_RAW_BASE_URL}/{owner}/{repo}/{ref}/{path}"
