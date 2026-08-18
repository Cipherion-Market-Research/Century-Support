"""Fetch and parse the live site's public sitemap.xml -- a DISCOVERY
signal for which pages exist, not the tracked-page scope itself.

See sitemap_parity.py's module docstring for how sitemap membership,
Config.KNOWN_NOINDEX_SLUGS, and Config.EXCLUDED_SLUGS combine into the
scope this service is actually expected to track.

Parsed with stdlib xml.etree (no new dependency). The live fetch is a
separate, injectable module (mirrors parity_probe.py's LiveFetcher
Protocol) so tests never touch a real network -- only a fixture-backed
double satisfies SitemapFetcher in tests/.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional, Protocol
from urllib.parse import urlparse

from drift_monitor.config import Config
from drift_monitor.retry import retry_async

# sitemaps.org's standard namespace. Matched tolerantly alongside a bare,
# unnamespaced <loc> so a hand-fixtured or slightly nonstandard document
# still parses.
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


class SitemapFetchError(RuntimeError):
    """Raised on any network, HTTP-status, or XML-parse failure. Callers
    (main.py's sitemap-parity step) must catch this and skip the check for
    that cycle -- a sitemap outage must never crash the poller."""


class SitemapFetcher(Protocol):
    async def fetch_sitemap(self, url: str) -> bytes: ...


class HttpSitemapFetcher:
    """Real implementation: plain GET against the live sitemap URL, with
    the same retry/backoff policy as GitHubClient's fetches."""

    def __init__(self, session):
        self.session = session

    async def fetch_sitemap(self, url: str) -> bytes:
        import aiohttp

        async def _do() -> bytes:
            timeout = aiohttp.ClientTimeout(total=Config.HTTP_TIMEOUT_S)
            async with self.session.get(url, timeout=timeout) as resp:
                resp.raise_for_status()
                return await resp.read()

        return await retry_async(_do)


def slug_from_loc(loc_url: str) -> str:
    """https://ciphex.io/foo -> "foo"; https://ciphex.io/ (or a bare
    https://ciphex.io) -> "index" -- the same convention
    data/kb_source/inventory.json and page_manifest.py use for the root
    page's slug."""
    path = urlparse(loc_url).path
    slug = path.strip("/")
    return slug if slug else "index"


def parse_sitemap_xml(xml_bytes: bytes) -> list[str]:
    """Parse a sitemap.xml document into an ordered list of page slugs,
    one per <url><loc> entry (namespace-tolerant: matches both the
    standard sitemaps.org-namespaced <loc> and a bare, unnamespaced one).
    Pure function -- no I/O -- so it is directly unit-testable against a
    fixture file."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise SitemapFetchError(f"sitemap.xml is not valid XML: {e}") from e

    slugs = []
    for el in root.iter():
        if el.tag in (f"{_SITEMAP_NS}loc", "loc"):
            loc = (el.text or "").strip()
            if loc:
                slugs.append(slug_from_loc(loc))
    return slugs


async def fetch_sitemap_slugs(fetcher: SitemapFetcher, url: Optional[str] = None) -> list[str]:
    """Fetch + parse the sitemap in one step. Raises SitemapFetchError on
    any failure (network, HTTP status, or malformed XML) -- never returns
    a partial/best-effort result, so callers can treat "no exception" as
    "safe to compare".

    `url` defaults to Config.SITEMAP_URL, re-read at call time (not bound
    as a function default) so DRIFT_SITEMAP_URL overrides and test
    monkeypatches both take effect.
    """
    sitemap_url = url if url is not None else Config.SITEMAP_URL
    try:
        xml_bytes = await fetcher.fetch_sitemap(sitemap_url)
    except SitemapFetchError:
        raise
    except Exception as e:
        raise SitemapFetchError(f"failed to fetch sitemap at {sitemap_url}: {e}") from e

    return parse_sitemap_xml(xml_bytes)
