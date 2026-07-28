"""Per-page sha256 baseline manifest under drift_monitor/baselines/.

The manifest (drift_monitor/baselines/manifest.json) records, per watched
page: the repo path it corresponds to, the sha256 of its normalized
chrome-free body text, and where that snapshot came from. The full
normalized text is also kept alongside (baselines/text/<slug>.txt) so the
diff engine has something to diff against, not just a hash to compare.

Seeding: per the WP-7a brief, the initial baseline is seeded from
data/kb_source/ (the harvested chrome-free extraction of the live site on
2026-07-20, already validated by WP-2/WP-4). Because that corpus is
Markdown extracted by a different tool than this module's own
html_normalize.extract_body_text (which runs against raw ciphex-website
HTML), the two won't byte-for-byte agree on whitespace/line-breaking even
when the underlying copy is identical -- so the FIRST real poll against
the live repo should be expected to raise line-level noise on every page.
`reseed_from_repo()` (fetches current src/*.html through the injected
GitHub client and rebuilds the manifest from THIS module's own
normalizer) is the recommended way to establish a clean, self-consistent
baseline before this service goes live; `seed_from_kb_source()` exists to
satisfy the literal brief and to give tests/demo runs an immediately
usable baseline without any network access.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from drift_monitor.config import Config
from drift_monitor.html_normalize import normalize_plain_text
from drift_monitor.page_manifest import WatchedPage, load_watched_pages

MANIFEST_VERSION = 1


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class PageBaseline:
    slug: str
    repo_path: str
    sha256: str
    seeded_from: str
    seeded_on: str
    tracked_ref: str = Config.TRACKED_REF


class BaselineManifest:
    """Reads/writes drift_monitor/baselines/manifest.json plus the
    per-page normalized-text snapshots it references."""

    def __init__(self, baseline_dir: Optional[str] = None):
        # Resolved at call time, not bound at import time -- Config.BASELINE_DIR
        # must be re-read here so tests can monkeypatch it (a `= Config.X`
        # default would freeze the value the moment this module is imported).
        self.baseline_dir = Path(baseline_dir if baseline_dir is not None else Config.BASELINE_DIR)
        self.text_dir = self.baseline_dir / "text"
        self.manifest_path = self.baseline_dir / "manifest.json"
        self._pages: dict[str, PageBaseline] = {}

    # -- persistence --

    def load(self) -> "BaselineManifest":
        if not self.manifest_path.exists():
            self._pages = {}
            return self
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._pages = {
            slug: PageBaseline(**entry) for slug, entry in raw.get("pages", {}).items()
        }
        return self

    def save(self) -> None:
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.text_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": MANIFEST_VERSION,
            "pages": {slug: asdict(pb) for slug, pb in self._pages.items()},
        }
        tmp_path = self.manifest_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
        tmp_path.replace(self.manifest_path)

    # -- accessors --

    def get(self, slug: str) -> Optional[PageBaseline]:
        return self._pages.get(slug)

    def get_text(self, slug: str) -> Optional[str]:
        path = self.text_dir / f"{slug}.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def slugs(self) -> list[str]:
        return list(self._pages.keys())

    # -- mutation --

    def set_page(self, slug: str, repo_path: str, text: str, *, seeded_from: str) -> None:
        self.text_dir.mkdir(parents=True, exist_ok=True)
        (self.text_dir / f"{slug}.txt").write_text(text, encoding="utf-8")
        self._pages[slug] = PageBaseline(
            slug=slug,
            repo_path=repo_path,
            sha256=sha256_text(text),
            seeded_from=seeded_from,
            seeded_on=utcnow_iso(),
        )

    # -- seeding --

    def seed_from_kb_source(
        self, kb_source_dir: str = Config.KB_SOURCE_DIR, pages: Optional[list[WatchedPage]] = None
    ) -> None:
        """Seed every watched page's baseline from its data/kb_source/pages/<slug>.md
        extraction (literal brief instruction; see module docstring for the
        format-consistency caveat vs. a live-repo reseed)."""
        pages = pages if pages is not None else load_watched_pages(kb_source_dir)
        for page in pages:
            md_path = Path(kb_source_dir) / "pages" / f"{page.slug}.md"
            if not md_path.exists():
                continue
            raw_text = md_path.read_text(encoding="utf-8")
            normalized = normalize_plain_text(raw_text)
            self.set_page(
                page.slug, page.repo_path, normalized, seeded_from=f"kb_source:{md_path}"
            )

    async def reseed_from_repo(self, github_client, pages: Optional[list[WatchedPage]] = None) -> None:
        """Rebuild the baseline from the current ciphex-website main
        content, using this module's own normalizer -- the recommended
        real bootstrap so the baseline is self-consistent with every
        future diff (see module docstring)."""
        from drift_monitor.html_normalize import extract_body_text

        pages = pages if pages is not None else load_watched_pages()
        for page in pages:
            html_bytes = await github_client.fetch_raw(page.repo_path, Config.TRACKED_REF)
            normalized = extract_body_text(html_bytes.decode("utf-8"))
            self.set_page(
                page.slug,
                page.repo_path,
                normalized,
                seeded_from=f"repo:{page.repo_path}@{Config.TRACKED_REF}",
            )
