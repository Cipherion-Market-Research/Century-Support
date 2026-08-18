"""Entrypoint for the content drift monitor (WP-7a).

Modes:
  - `python -m drift_monitor.main serve`            (default) run the
    scheduled poll loop, the weekly parity probe, and the health server.
  - `python -m drift_monitor.main seed-baseline`     one-shot: seed
    drift_monitor/baselines/ from data/kb_source/ (see baseline.py).
  - `python -m drift_monitor.main reseed-baseline`   one-shot: rebuild the
    baseline from the live ciphex-website repo (recommended before the
    service first goes live -- see baseline.py's module docstring).

`serve` fails loudly at startup (see check_startup_requirements()) if
DRIFT_CONTENT_ENABLED is true and DRIFT_GITHUB_TOKEN is not set --
unauthenticated GitHub access to the tracked repo currently 404s
(verified 2026-07-28), and a poll loop that can't reach GitHub should not
start silently.

Unlike kpi_sync/ and pubs_rag/ (each self-contained with Railway's "Root
Directory" pointed at the package itself), this service reads facts.yaml
and data/kb_source/ from the repo root via the `facts_store` package, so
its Railway Root Directory must stay the REPO ROOT, with this file
invoked as `python -m drift_monitor.main serve` (see railway.json).

Scheduling: a long-running process with an internal asyncio loop
(mirroring kpi_sync/pollers/base.py's run_forever pattern), not a Railway
cron job. Justification: this service is stateful across cycles (the
baseline manifest, the fingerprint-dedup state, and the commits-API poll
cursor all need to persist between polls), so a cron invocation would
either need a persistent volume mounted anyway or would reload/re-hash
the whole baseline from scratch every run for no benefit. A long-running
service keeps that state warm in the same filesystem the whole time,
gives us in-process retry/backoff and graceful SIGTERM shutdown for free
(same operational model as kpi_sync and pubs_rag), and needs no new
Railway feature.
"""
import asyncio
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

from drift_monitor.baseline import BaselineManifest
from drift_monitor.config import Config
from drift_monitor.gh_pr import GhCliPrCreator, NoOpPrCreator
from drift_monitor.github_client import GitHubClient
from drift_monitor.health_server import run_health_server
from drift_monitor.logging_setup import get_logger, setup_logging
from drift_monitor.notify import notify_new_finding
from drift_monitor.page_manifest import load_watched_pages
from drift_monitor.parity_probe import HttpLiveFetcher, run_parity_probe, write_parity_report
from drift_monitor.poller import run_poll_cycle
from drift_monitor.pr_preview import build_pr_preview
from drift_monitor.report import write_shadow_report
from drift_monitor.sitemap import HttpSitemapFetcher, SitemapFetchError, fetch_sitemap_slugs
from drift_monitor.sitemap_parity import check_sitemap_parity, write_sitemap_parity_report
from drift_monitor.state import FindingsState, PollState
from facts_store.loader import FactsStore

logger = get_logger("drift_monitor.main")


class StartupConfigError(RuntimeError):
    """Raised by check_startup_requirements() when the service can't
    safely start (see its docstring)."""


def check_startup_requirements() -> None:
    """Fail loudly instead of silently polling and 404ing forever.

    Verified 2026-07-28 by direct, live `curl` against the GitHub API (no
    auth headers): unauthenticated requests to both
    api.github.com/repos/Cipherion-Market-Research/ciphex-website (404)
    and its raw-content path (404) fail, while a control request to a
    known-public repository returned 200 in the same check -- so this is
    repo-specific, not a connectivity artifact. A content-drift poll loop
    started without a token would spend every cycle 404ing against the
    tracked repo and never detect anything, which is worse than not
    starting at all.

    Gated on Config.CONTENT_ENABLED, the single kill switch for the whole
    7a lane (content-drift polling AND the parity probe, which also reads
    the tracked repo): DRIFT_CONTENT_ENABLED=false never requires a
    token. Never logs or otherwise includes Config.GITHUB_TOKEN's value
    -- only whether it is present.
    """
    if Config.CONTENT_ENABLED and not Config.GITHUB_TOKEN:
        raise StartupConfigError(
            "DRIFT_CONTENT_ENABLED is true but DRIFT_GITHUB_TOKEN is not set. "
            "Unauthenticated GitHub access to the tracked repo "
            f"({Config.GITHUB_REPO_OWNER}/{Config.GITHUB_REPO_NAME}) currently returns 404 "
            "(verified 2026-07-28) -- refusing to start a poll loop that would silently "
            "fail every cycle. Set DRIFT_GITHUB_TOKEN, or set DRIFT_CONTENT_ENABLED=false "
            "to run this service with only its health server active."
        )


async def run_content_poll_once(session: aiohttp.ClientSession) -> list:
    pages = load_watched_pages()
    github_client = GitHubClient(session)
    store = FactsStore.load(Config.FACTS_YAML_PATH)
    baseline = BaselineManifest().load()
    findings_state = FindingsState().load()
    poll_state = PollState().load()

    new_findings = await run_poll_cycle(pages, github_client, store, baseline, findings_state, poll_state)

    if new_findings:
        if Config.OPEN_PRS:
            pr_creator = GhCliPrCreator(repo=f"{Config.GITHUB_REPO_OWNER}/{Config.GITHUB_REPO_NAME}")
            preview = build_pr_preview(new_findings)
            result = pr_creator.create_pr(preview)
            logger.info(
                "PR mode: prepared consolidated PR",
                extra={"event": "pr_prepared", "path": str(result)},
            )
            # "Every drift PR moves the baseline snapshot with the fact"
            # (docs/BUILD_HANDOFF.md WP-7a) -- else the same drift
            # re-flags on every future poll. Bundled with PR prep, not
            # shadow mode, where the fingerprint-dedup state alone is
            # what suppresses repeat reports.
            for finding in new_findings:
                baseline.set_page(
                    finding.slug,
                    finding.repo_path,
                    finding.current_text,
                    seeded_from=f"pr:{finding.fingerprint}@{Config.TRACKED_REF}",
                )
                findings_state.record(finding.slug, finding.fingerprint, report_path="(pr)", status="pr_prepared")
            baseline.save()
        else:
            for finding in new_findings:
                report_path = write_shadow_report(finding)
                findings_state.record(finding.slug, finding.fingerprint, report_path=str(report_path))
                notify_new_finding(finding, str(report_path))
                logger.info(
                    "shadow report written",
                    extra={"event": "shadow_report_written", "slug": finding.slug, "path": str(report_path)},
                )

    findings_state.save()
    poll_state.save()
    return new_findings


async def run_parity_probe_once(session: aiohttp.ClientSession) -> list:
    all_pages = {p.slug: p for p in load_watched_pages()}
    sentinel_pages = [all_pages[slug] for slug in Config.PARITY_SENTINEL_SLUGS if slug in all_pages]
    github_client = GitHubClient(session)
    live_fetcher = HttpLiveFetcher(session)

    results = await run_parity_probe(sentinel_pages, live_fetcher, github_client)
    write_parity_report(results)
    for r in results:
        if not r.matches:
            logger.warning("live/repo parity mismatch", extra={"event": "parity_mismatch", "slug": r.slug})
    return results


async def run_sitemap_parity_once(session: aiohttp.ClientSession) -> list:
    """Compare the live sitemap.xml against this service's tracked page
    manifest (see page_manifest.load_watched_pages()) and emit advisory
    sitemap_new_page / sitemap_removed_page / sitemap_excluded_present
    findings for a human to act on. Never mutates the page manifest,
    inventory, or baseline -- propose-only, same posture as content-drift
    findings.

    Sitemap fetch failures are swallowed here (one warn log) rather than
    propagated -- an unreachable sitemap must never crash the poller, it
    just means this cycle's check is skipped (see sitemap.SitemapFetchError).
    """
    try:
        sitemap_slugs = await fetch_sitemap_slugs(HttpSitemapFetcher(session))
    except SitemapFetchError:
        logger.warning(
            "sitemap fetch failed; skipping sitemap-parity check this cycle",
            extra={"event": "sitemap_fetch_failed"},
            exc_info=True,
        )
        return []

    tracked_slugs = {p.slug for p in load_watched_pages()}
    all_findings = check_sitemap_parity(sitemap_slugs, tracked_slugs)

    findings_state = FindingsState().load()
    new_findings = []
    for finding in all_findings:
        # Namespaced under "sitemap:" in FindingsState's per-slug dedup
        # table so this check's findings never collide with a
        # content-drift PageFinding recorded against the same bare slug.
        state_key = f"sitemap:{finding.slug}"
        if findings_state.seen(state_key, finding.fingerprint):
            logger.info(
                "duplicate sitemap finding suppressed",
                extra={"event": "duplicate_suppressed", "slug": finding.slug, "fingerprint": finding.fingerprint},
            )
            continue
        logger.info(
            finding.detail,
            extra={"event": finding.kind, "slug": finding.slug, "fingerprint": finding.fingerprint},
        )
        findings_state.record(state_key, finding.fingerprint, report_path="(sitemap-parity)", status=finding.kind)
        new_findings.append(finding)

    if new_findings:
        report_path = write_sitemap_parity_report(new_findings)
        logger.info(
            "sitemap parity report written",
            extra={"event": "sitemap_parity_report_written", "path": str(report_path)},
        )

    findings_state.save()
    return new_findings


async def _interruptible_sleep(seconds: int, stop_event: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def content_poll_loop(session: aiohttp.ClientSession, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        if Config.CONTENT_ENABLED:
            try:
                await run_content_poll_once(session)
            except Exception:
                logger.error("content poll cycle failed", extra={"event": "poll_cycle_failed"}, exc_info=True)
        else:
            logger.info("content drift monitor disabled (DRIFT_CONTENT_ENABLED=false)", extra={"event": "disabled"})
        await _interruptible_sleep(Config.POLL_INTERVAL_S, stop_event)


async def parity_probe_loop(session: aiohttp.ClientSession, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        if Config.CONTENT_ENABLED:
            try:
                await run_parity_probe_once(session)
            except Exception:
                logger.error("parity probe cycle failed", extra={"event": "parity_cycle_failed"}, exc_info=True)
            try:
                await run_sitemap_parity_once(session)
            except Exception:
                # run_sitemap_parity_once already swallows a fetch failure
                # internally (SitemapFetchError -> warn + skip); this is a
                # last-resort net for anything else so the weekly loop
                # itself never dies from this step either.
                logger.error(
                    "sitemap parity cycle failed", extra={"event": "sitemap_parity_cycle_failed"}, exc_info=True
                )
        await _interruptible_sleep(Config.PARITY_INTERVAL_S, stop_event)


async def serve() -> None:
    setup_logging(Config.LOG_LEVEL)
    try:
        check_startup_requirements()
    except StartupConfigError as e:
        logger.error(str(e), extra={"event": "startup_config_error"})
        raise
    poll_state = PollState().load()
    runner = await run_health_server(poll_state, Config.HEALTH_HOST, Config.HEALTH_PORT)
    logger.info("drift_monitor started", extra={"event": "startup"})

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.create_task(content_poll_loop(session, stop_event)),
            asyncio.create_task(parity_probe_loop(session, stop_event)),
        ]
        await stop_event.wait()
        logger.info("shutting down", extra={"event": "shutdown"})
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    await runner.cleanup()


def seed_baseline() -> None:
    setup_logging(Config.LOG_LEVEL)
    manifest = BaselineManifest()
    manifest.load()
    manifest.seed_from_kb_source()
    manifest.save()
    logger.info(f"seeded baseline for {len(manifest.slugs())} pages from {Config.KB_SOURCE_DIR}")


async def reseed_baseline() -> None:
    setup_logging(Config.LOG_LEVEL)
    async with aiohttp.ClientSession() as session:
        github_client = GitHubClient(session)
        manifest = BaselineManifest()
        manifest.load()
        await manifest.reseed_from_repo(github_client)
        manifest.save()
    logger.info(f"reseeded baseline for {len(manifest.slugs())} pages from live repo ({Config.TRACKED_REF})")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if mode == "serve":
        try:
            asyncio.run(serve())
        except StartupConfigError as e:
            print(f"drift_monitor: startup configuration error: {e}", file=sys.stderr)
            sys.exit(1)
    elif mode == "seed-baseline":
        seed_baseline()
    elif mode == "reseed-baseline":
        asyncio.run(reseed_baseline())
    else:
        print("usage: python -m drift_monitor.main [serve|seed-baseline|reseed-baseline]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
