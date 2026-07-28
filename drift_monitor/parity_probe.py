"""Weekly live-vs-repo parity probe for 3 sentinel pages.

Separate concern from the main content-drift pipeline: drift_check.py
asks "did the REPO SOURCE change since our baseline". This module asks a
narrower safety question -- "does the LIVE page still match what the
repo source says", which catches a stale deploy (repo says X, live site
still shows the old Y) or a live-only hotfix that never landed in the
repo. It never proposes a fact edit; it only reports a mismatch for a
human to investigate.

The live-page fetch is a separate, injectable network module (distinct
from GitHubClient) so tests can supply a fixture-backed double -- no live
network in tests, per the WP-7a brief.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

from drift_monitor.config import Config
from drift_monitor.diff_engine import compute_hunks, unified_diff_text
from drift_monitor.html_normalize import extract_body_text


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class LiveFetcher(Protocol):
    async def fetch_live_page(self, url: str) -> bytes: ...


class HttpLiveFetcher:
    """Real implementation: plain GET against the live site."""

    def __init__(self, session):
        self.session = session

    async def fetch_live_page(self, url: str) -> bytes:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=Config.HTTP_TIMEOUT_S)
        async with self.session.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.read()


@dataclass
class ParityResult:
    slug: str
    live_url: str
    repo_path: str
    matches: bool
    diff_text: str = ""
    checked_at: str = field(default_factory=utcnow_iso)


async def check_page_parity(
    slug: str, repo_path: str, live_url: str, live_fetcher: LiveFetcher, github_client
) -> ParityResult:
    live_bytes = await live_fetcher.fetch_live_page(live_url)
    repo_bytes = await github_client.fetch_raw(repo_path, Config.TRACKED_REF)

    live_text = extract_body_text(live_bytes.decode("utf-8"))
    repo_text = extract_body_text(repo_bytes.decode("utf-8"))

    hunks = compute_hunks(repo_text, live_text)
    matches = not hunks
    diff_text = "" if matches else unified_diff_text(repo_text, live_text, fromfile=f"repo:{slug}", tofile=f"live:{slug}")

    return ParityResult(
        slug=slug, live_url=live_url, repo_path=repo_path, matches=matches, diff_text=diff_text
    )


async def run_parity_probe(
    sentinel_pages: list, live_fetcher: LiveFetcher, github_client
) -> list:
    """`sentinel_pages` is a list of WatchedPage. Returns one ParityResult
    per page; callers decide what to do with mismatches (log + write a
    report -- see write_parity_report)."""
    results = []
    for page in sentinel_pages:
        result = await check_page_parity(
            page.slug, page.repo_path, page.source_url, live_fetcher, github_client
        )
        results.append(result)
    return results


def render_parity_report_markdown(results: list) -> str:
    lines = ["# Live-vs-repo parity probe", "", f"Checked at: {utcnow_iso()}", ""]
    for r in results:
        status = "OK (match)" if r.matches else "MISMATCH"
        lines.append(f"## {r.slug} — {status}")
        lines.append(f"- Live: {r.live_url}")
        lines.append(f"- Repo: `{r.repo_path}` (ref: `{Config.TRACKED_REF}`)")
        if not r.matches:
            lines.extend(["", "```diff", r.diff_text, "```"])
        lines.append("")
    return "\n".join(lines)


def write_parity_report(results: list, reports_dir: Optional[str] = None) -> Path:
    directory = Path(reports_dir if reports_dir is not None else Config.REPORTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    ts = utcnow_iso().replace(":", "").replace("-", "")
    path = directory / f"{ts}-parity-probe.md"
    path.write_text(render_parity_report_markdown(results), encoding="utf-8")
    return path
