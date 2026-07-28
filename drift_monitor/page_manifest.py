"""The list of pages this service watches, and the slug <-> repo-path
mapping between data/kb_source/ (the seed corpus) and ciphex-website's
src/*.html entry files.

Confirmed pattern: pubs_rag/config.py's PUBLICATION_INDEX_PATHS shows
ecosystem-publications and ecosystem-updates each live at
src/<slug>.html; data/kb_source/inventory.json's page slugs (which are
literally the URL path segment, "index" for "/") follow the same
convention for every other marketing page in the corpus.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from drift_monitor.config import Config


@dataclass(frozen=True)
class WatchedPage:
    slug: str
    repo_path: str
    source_url: str
    kb_source_local_path: Optional[str] = None
    kb_source_sha256: Optional[str] = None


def repo_path_for_slug(slug: str) -> str:
    return f"{Config.WATCHED_PATH_PREFIX}{slug}{Config.WATCHED_PATH_SUFFIX}"


def load_watched_pages(kb_source_dir: str = Config.KB_SOURCE_DIR) -> list[WatchedPage]:
    """Build the watch list from data/kb_source/inventory.json's "page"
    entries (PDFs are WP-4's concern, not this service's)."""
    inventory_path = Path(kb_source_dir) / "inventory.json"
    with open(inventory_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    pages = []
    for entry in inventory:
        if entry.get("kind") != "page":
            continue
        slug = entry["slug"]
        pages.append(
            WatchedPage(
                slug=slug,
                repo_path=repo_path_for_slug(slug),
                source_url=entry["source_url"],
                kb_source_local_path=entry.get("local_path"),
                kb_source_sha256=entry.get("sha256"),
            )
        )
    return pages
