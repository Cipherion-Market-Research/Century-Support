#!/usr/bin/env python3
"""Committed harvester for the website-pages knowledge corpus (Sprint 3).

The hand-harvested data/kb_source/pages/*.md corpus (captured 2026-07-29)
is stale -- e.g. the leadership page alone was reworked twice since. This
script replaces that manual process with a reproducible one: read each
in-scope page's SERVER-RENDERED SOURCE straight from the ciphex-website
repo at a given git ref (never a live HTTP fetch, and never that repo's
working tree -- see --repo-path below), strip it to readable text, and
write data/kb_source/pages/<slug>.md + refresh its data/kb_source/
inventory.json entry.

Usage:
    python scripts/harvest_pages.py <repo-path> [--ref origin/main]
        [--out-dir data/kb_source/pages] [--inventory data/kb_source/inventory.json]
        [--sitemap-url https://ciphex.io/sitemap.xml] [--sitemap-file PATH]
        [--slugs slug1,slug2,...] [--fetch] [--dry-run]

  <repo-path>   Local checkout of Cipherion-Market-Research/ciphex-website
                (e.g. /Users/matt/Desktop/Cipherion/ciphex-frontend/ciphex-website).
                Content is ALWAYS read via `git show <ref>:src/<slug>.html`
                -- the checkout's working tree is never trusted (it may be
                stale, mid-edit, or ahead of what's actually on the ref).
  --ref         Git ref to read from. Defaults to "origin/main". Pass
                --fetch to run `git fetch origin` in <repo-path> first, so
                a stale local `origin/main` doesn't silently under-harvest.
  --sitemap-file  Read sitemap.xml bytes from a local file instead of the
                network (offline/testing; skips --sitemap-url entirely).
  --slugs       Comma-separated explicit slug list, bypassing sitemap
                discovery entirely (targeted re-harvest of a few pages).
  --dry-run     Parse and report, but never write files or mutate inventory.

Page scope (owner-approved formula, drift_monitor/sitemap_parity.py):

    expected_tracked = (sitemap_slugs | KNOWN_NOINDEX_SLUGS) - EXCLUDED_SLUGS

reused directly from drift_monitor.sitemap_parity/config so this script can
never drift from the sitemap-parity check's own definition of "in scope".
insights-and-publications is in EXCLUDED_SLUGS (2026-08-18 Bot Parameter
Requirements: excluded from bot knowledge). 404 and unavailable are utility
pages, never part of either the sitemap or KNOWN_NOINDEX_SLUGS, but are
excluded explicitly below as documentation of intent (belt-and-suspenders
against either set ever accidentally growing to include them).

Public repo: this script and everything it writes must never mention Claude,
Anthropic, or any AI/vendor tooling -- harvested content headers included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from drift_monitor.config import Config as DriftConfig  # noqa: E402
from drift_monitor.sitemap import parse_sitemap_xml  # noqa: E402
from drift_monitor.sitemap_parity import compute_expected_tracked  # noqa: E402

# Utility pages that are never part of the bot-knowledge harvest even if
# they somehow appeared in the sitemap-parity formula's output (they don't
# today -- see module docstring).
_UTILITY_SLUGS = frozenset({"404", "unavailable"})

_WATCHED_PATH_PREFIX = "src/"
_WATCHED_PATH_SUFFIX = ".html"


# ─────────────────────────── page scope ───────────────────────────


def fetch_sitemap_bytes(url: str, timeout_s: float = 20.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout_s) as resp:  # noqa: S310 (admin CLI, fixed https URL)
        return resp.read()


def compute_harvest_scope(sitemap_slugs: list[str]) -> list[str]:
    """Pure function: sitemap slugs -> sorted list of slugs this script
    harvests. Reuses drift_monitor's own sitemap-parity formula (see module
    docstring) so the two never diverge."""
    expected = compute_expected_tracked(sitemap_slugs)
    return sorted(expected - _UTILITY_SLUGS)


# ─────────────────────────── git source read ───────────────────────────


class GitShowError(RuntimeError):
    pass


def git_fetch(repo_path: str, remote: str = "origin") -> None:
    result = subprocess.run(
        ["git", "-C", repo_path, "fetch", remote],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitShowError(f"git fetch {remote} failed in {repo_path!r}: {result.stderr.strip()}")


def read_repo_file(repo_path: str, ref: str, repo_relative_path: str) -> str:
    """`git show <ref>:<path>` -- reads the committed blob directly, never
    the working tree (which may be stale/mid-edit/ahead of the ref)."""
    result = subprocess.run(
        ["git", "-C", repo_path, "show", f"{ref}:{repo_relative_path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitShowError(
            f"git show {ref}:{repo_relative_path} failed in {repo_path!r}: {result.stderr.strip()}"
        )
    return result.stdout


# ─────────────────────────── HTML -> markdown extraction ───────────────────────────


# Tags whose content (and any nested markup) is never body copy: scripts,
# styles, document head, embedded SVG icons, and navigation/footer chrome.
# The site's nav/footer render client-side from empty custom elements
# (<site-nav></site-nav>, <site-footer></site-footer> -- see components.js)
# so this is belt-and-suspenders, not load-bearing for the current markup:
# the <main id="main-content"> scope below already excludes them since
# they sit outside <main> in every page's source.
_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "template",
        "noscript",
        "head",
        "svg",
        "nav",
        "header",
        "footer",
        "site-nav",
        "site-footer",
        "site-header",
    }
)

# Inline tags: their text merges into the surrounding paragraph rather than
# starting a new one (e.g. a <span> wrapping a couple of emphasized words
# inside a heading). Everything else (div, p, li, h1-h6, section, table
# cells, ...) is a paragraph boundary.
_INLINE_TAGS = frozenset(
    {
        "a",
        "span",
        "em",
        "strong",
        "b",
        "i",
        "u",
        "small",
        "sup",
        "sub",
        "abbr",
        "code",
        "picture",
        "source",
        "img",
        "br",
        "wbr",
    }
)

_WHITESPACE_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


class MainTextExtractor(HTMLParser):
    """Stdlib html.parser extraction of a page's <title> and the readable
    text inside <main id="main-content">, one paragraph per block-level
    element -- deliberately no bs4/lxml dependency (see module docstring).

    Text nodes are joined at "paragraph" granularity: a block-level tag's
    open/close flushes the current buffer as one paragraph; inline tags
    (span/a/em/strong/...) merge into whatever paragraph is already open.
    This matches how the site's markup is actually structured -- each
    stat/label/list-item/heading is its own block-level element wrapping a
    single short text run, with <em>/<span> used only for partial-text
    emphasis *within* one of those runs.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.paragraphs: list[str] = []
        self._buf: list[str] = []
        self._in_title = False
        self._main_depth = 0
        self._skip_stack: list[str] = []

    # -- internal --

    def _flush(self) -> None:
        text = _clean("".join(self._buf))
        self._buf = []
        if text:
            self.paragraphs.append(text)

    # -- HTMLParser hooks --

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self._in_title = True
            return
        if self._skip_stack:
            if tag in _SKIP_TAGS:
                self._skip_stack.append(tag)
            return
        if tag in _SKIP_TAGS:
            self._skip_stack.append(tag)
            self._flush()
            return
        if tag == "main":
            self._main_depth += 1
            return
        if self._main_depth == 0:
            return
        if tag not in _INLINE_TAGS:
            self._flush()

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            return
        if self._skip_stack:
            if self._skip_stack[-1] == tag:
                self._skip_stack.pop()
            return
        if tag == "main":
            if self._main_depth > 0:
                self._flush()
                self._main_depth -= 1
            return
        if self._main_depth == 0:
            return
        if tag not in _INLINE_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
            return
        if self._skip_stack:
            return
        if self._main_depth == 0:
            return
        self._buf.append(data)

    @property
    def title(self) -> str:
        return _clean("".join(self.title_parts))


def extract_page(html: str) -> tuple[str, list[str]]:
    """Returns (title, paragraphs) for one page's raw source HTML."""
    parser = MainTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.title, parser.paragraphs


def render_markdown(*, title: str, source_url: str, fetched_date: str, paragraphs: list[str]) -> str:
    frontmatter = (
        "<!--\n"
        f"source_url: {source_url}\n"
        f"fetched: {fetched_date}\n"
        f"page_title: {title}\n"
        "kind: site page copy (harvested via git show, scripts/harvest_pages.py)\n"
        "-->\n"
    )
    body = "\n\n".join(paragraphs)
    return f"{frontmatter}\n# {title}\n\n{body}\n"


# ─────────────────────────── harvest result ───────────────────────────


@dataclass
class HarvestResult:
    slug: str
    ok: bool
    reason: str = ""
    title: str = ""
    words: int = 0
    changed: bool = False
    low_quality: bool = False
    low_quality_reason: str = ""


# A page whose extraction is suspiciously thin is flagged, not failed --
# it still gets written (a short-but-real page is legitimate, e.g. a
# disclosure stub), but the operator running this script should look at it
# before trusting it as a seed for pubs_rag ingestion.
_LOW_QUALITY_WORD_THRESHOLD = 40


def harvest_one_page(
    *,
    slug: str,
    repo_path: str,
    ref: str,
    source_url: str,
    fetched_date: str,
) -> tuple[Optional[HarvestResult], Optional[str]]:
    """Returns (result, markdown_text). markdown_text is None when the page
    could not be read/parsed at all (result.ok is False)."""
    repo_relative_path = f"{_WATCHED_PATH_PREFIX}{slug}{_WATCHED_PATH_SUFFIX}"
    try:
        html = read_repo_file(repo_path, ref, repo_relative_path)
    except GitShowError as e:
        return HarvestResult(slug=slug, ok=False, reason=str(e)), None

    title, paragraphs = extract_page(html)
    if not title:
        return HarvestResult(slug=slug, ok=False, reason="no <title> found in source HTML"), None
    if not paragraphs:
        return HarvestResult(slug=slug, ok=False, reason="no readable text found inside <main>"), None

    markdown = render_markdown(
        title=title, source_url=source_url, fetched_date=fetched_date, paragraphs=paragraphs
    )
    words = sum(len(p.split()) for p in paragraphs)
    low_quality = words < _LOW_QUALITY_WORD_THRESHOLD
    low_quality_reason = (
        f"only {words} words extracted (< {_LOW_QUALITY_WORD_THRESHOLD}) -- verify <main> markup didn't change"
        if low_quality
        else ""
    )
    result = HarvestResult(
        slug=slug,
        ok=True,
        title=title,
        words=words,
        low_quality=low_quality,
        low_quality_reason=low_quality_reason,
    )
    return result, markdown


# ─────────────────────────── inventory ───────────────────────────


def load_inventory(inventory_path: Path) -> list[dict]:
    if not inventory_path.exists():
        return []
    return json.loads(inventory_path.read_text(encoding="utf-8"))


def upsert_inventory_entry(inventory: list[dict], entry: dict) -> list[dict]:
    """Replace the "page" entry matching entry['slug'] in place (preserving
    its position in the file), or append if it's new. Never touches
    non-page entries or page entries outside the harvest run."""
    for i, existing in enumerate(inventory):
        if existing.get("kind") == "page" and existing.get("slug") == entry["slug"]:
            inventory[i] = entry
            return inventory
    inventory.append(entry)
    return inventory


def source_url_for_slug(slug: str, site_base_url: str) -> str:
    if slug == "index":
        return site_base_url.rstrip("/") + "/"
    return urljoin(site_base_url.rstrip("/") + "/", slug)


# ─────────────────────────── CLI ───────────────────────────


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo_path", help="Local checkout of the ciphex-website repo")
    parser.add_argument("--ref", default="origin/main", help='Git ref to read from (default: "origin/main")')
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "data" / "kb_source" / "pages"))
    parser.add_argument("--inventory", default=str(REPO_ROOT / "data" / "kb_source" / "inventory.json"))
    parser.add_argument("--sitemap-url", default=DriftConfig.SITEMAP_URL)
    parser.add_argument("--sitemap-file", default=None, help="Read sitemap.xml from a local file instead of the network")
    parser.add_argument("--slugs", default=None, help="Comma-separated explicit slug list (bypasses sitemap discovery)")
    parser.add_argument("--fetch", action="store_true", help="Run `git fetch origin` in repo-path before reading")
    parser.add_argument("--fetched-date", default=None, help="Override the recorded harvest date (default: today, UTC)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only; write nothing")
    args = parser.parse_args(argv)

    if args.fetch:
        print(f"fetching origin in {args.repo_path} ...")
        git_fetch(args.repo_path)

    if args.slugs:
        slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]
    else:
        if args.sitemap_file:
            sitemap_bytes = Path(args.sitemap_file).read_bytes()
        else:
            print(f"fetching sitemap: {args.sitemap_url}")
            sitemap_bytes = fetch_sitemap_bytes(args.sitemap_url)
        sitemap_slugs = parse_sitemap_xml(sitemap_bytes)
        slugs = compute_harvest_scope(sitemap_slugs)

    print(f"harvest scope ({len(slugs)} pages): {', '.join(slugs)}")

    fetched_date = args.fetched_date or date.today().isoformat()
    out_dir = Path(args.out_dir)
    inventory_path = Path(args.inventory)
    inventory = load_inventory(inventory_path)

    results: list[HarvestResult] = []
    for slug in slugs:
        source_url = source_url_for_slug(slug, DriftConfig.SITE_BASE_URL)
        result, markdown = harvest_one_page(
            slug=slug, repo_path=args.repo_path, ref=args.ref, source_url=source_url, fetched_date=fetched_date
        )
        results.append(result)

        if not result.ok:
            print(f"  [FAIL] {slug}: {result.reason}")
            continue

        local_path = out_dir / f"{slug}.md"
        md_bytes = markdown.encode("utf-8")
        sha256 = hashlib.sha256(md_bytes).hexdigest()

        existing_bytes = local_path.read_bytes() if local_path.exists() else None
        result.changed = existing_bytes != md_bytes

        flag = " [LOW-QUALITY]" if result.low_quality else ""
        print(
            f"  [ok]   {slug}: {result.words} words, "
            f"{'changed' if result.changed else 'unchanged'}{flag}"
        )
        if result.low_quality:
            print(f"         -> {result.low_quality_reason}")

        if args.dry_run:
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(md_bytes)

        entry = {
            "kind": "page",
            "slug": slug,
            "title": result.title,
            "date": None,
            "source_url": source_url,
            "local_path": f"data/kb_source/pages/{slug}.md",
            "sha256": sha256,
            "bytes": len(md_bytes),
            "extraction": "ok",
            "words": result.words,
            "harvested_at": fetched_date,
        }
        inventory = upsert_inventory_entry(inventory, entry)

    if not args.dry_run:
        inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    failures = [r for r in results if not r.ok]
    low_quality = [r for r in results if r.ok and r.low_quality]
    changed = [r for r in results if r.ok and r.changed]

    print()
    print(
        f"summary: {len(results) - len(failures)}/{len(results)} harvested, "
        f"{len(changed)} changed, {len(low_quality)} low-quality"
    )
    if low_quality:
        print("low-quality pages (verify manually): " + ", ".join(r.slug for r in low_quality))
    if failures:
        print("FAILED pages: " + ", ".join(f"{r.slug} ({r.reason})" for r in failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
