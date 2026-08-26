"""Retrieval function: query -> ranked chunks with citation metadata.

This is the function WP-5 (Century Core) calls for RAG answers; each result
carries everything C2's `fact`/`paragraph` blocks need to cite a source
(title + date + source_url) without a second lookup.

Serving quarantine (WP-7c): unapproved documents (not yet reviewed, or a
superseded/retracted version) are excluded by default -- a document must be
explicitly approved (`python -m pubs_rag.main approve`) before its chunks
are eligible for a user-facing answer. `include_unapproved=True` is the
admin/test escape hatch (e.g. `list-pending`-adjacent tooling); ordinary
callers (WP-5) never pass it. PUBS_RAG_QUARANTINE_ENABLED=false is the kill
switch that turns the whole filter off (serves regardless of approval
state), for parity with kpi_sync's per-source enable-flag pattern.

Serving recency cutoff (positioning-freshness policy, owner feedback
2026-08-19): a SEPARATE gate from the quarantine above. Live testers caught
the bot citing 2025-era internal-update PDFs as if their statements were
still current (the brand's positioning changed mid-2026). Config.
SERVE_DOCS_SINCE excludes documents dated before that boundary regardless
of `approved` state -- an approved-but-stale document is still excluded
here. See pubs_rag/date_utils.py for why this is a Python-side filter
rather than a SQL WHERE clause (documents.date is a free-text display
string, not a real date column).

Pages corpus (Sprint 3): retrieve_pages() below is a SEPARATE function
over a SEPARATE corpus (site_pages/page_chunks, see db.py) and does NOT
apply the recency cutoff above -- pages are the site's always-current
content; freshness is the harvester's job (scripts/harvest_pages.py),
not a serving-time filter. The WP-7c approval quarantine still applies.
"""
import logging
from dataclasses import dataclass

from pubs_rag.config import Config
from pubs_rag.date_utils import parse_cutoff, parse_document_date
from pubs_rag.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# Overfetch ceiling used only when the recency cutoff is active.
# db.search_chunks() ORDER BYs `embedding <=>` over the whole matching set
# and only then LIMITs -- Postgres computes+sorts the distance for every
# row regardless of top_k (see db.py: no ANN index at this corpus size,
# "tens of documents, low hundreds of chunks"), so asking for more rows
# than top_k costs nothing extra here. It's necessary for correctness: if
# we fetched only top_k rows and *then* filtered out stale ones, a
# high-scoring-but-stale chunk could occupy a slot a still-fresh,
# slightly-lower-scoring chunk should have won. 1000 is comfortably above
# any foreseeable chunk count at this corpus's scale.
_CUTOFF_OVERFETCH_LIMIT = 1000

# "Log once per slug" for excluded NULL/unparseable dates, so a single
# malformed document doesn't spam the log on every query -- module-level,
# so it naturally resets on process restart (the same point a changed
# SERVE_DOCS_SINCE env var takes effect; see config.py).
_logged_unparseable_slugs: set[str] = set()


@dataclass
class RetrievedChunk:
    content: str
    title: str
    date: str | None
    source_url: str
    slug: str
    kind: str
    score: float


@dataclass
class RetrievedPageChunk:
    content: str
    title: str
    slug: str
    score: float
    page_url: str
    captured_at: str | None = None


def _passes_recency_cutoff(row: dict, cutoff) -> bool:
    doc_date = parse_document_date(row.get("date"))
    if doc_date is None:
        slug = row.get("slug", "<unknown>")
        if slug not in _logged_unparseable_slugs:
            _logged_unparseable_slugs.add(slug)
            logger.warning(
                "retrieval: excluding document slug=%r (date=%r) -- date is missing or "
                "unparseable, and the serving recency cutoff (%s) treats that "
                "conservatively as excluded rather than guessing it's current",
                slug,
                row.get("date"),
                Config.SERVE_DOCS_SINCE,
            )
        return False
    return doc_date >= cutoff


async def retrieve(
    conn,
    provider: EmbeddingProvider,
    query: str,
    top_k: int = 5,
    *,
    include_unapproved: bool = False,
) -> list[RetrievedChunk]:
    from pubs_rag import db

    approved_only = Config.QUARANTINE_ENABLED and not include_unapproved
    cutoff = parse_cutoff(Config.SERVE_DOCS_SINCE)
    fetch_k = _CUTOFF_OVERFETCH_LIMIT if cutoff is not None else top_k

    [query_embedding] = provider.embed([query])
    rows = await db.search_chunks(conn, query_embedding, fetch_k, approved_only=approved_only)

    if cutoff is not None:
        rows = [row for row in rows if _passes_recency_cutoff(row, cutoff)]
    rows = rows[:top_k]

    return [
        RetrievedChunk(
            content=row["content"],
            title=row["title"],
            date=row["date"],
            source_url=row["source_url"],
            slug=row["slug"],
            kind=row["kind"],
            score=row["score"],
        )
        for row in rows
    ]


def page_url_for_slug(slug: str) -> str:
    """https://ciphex.io/<slug>; the homepage slug ("index") maps to the
    bare root, not "https://ciphex.io/index" -- same convention
    drift_monitor/sitemap.py's slug_from_loc() uses in reverse."""
    base = Config.SITE_BASE_URL.rstrip("/")
    if slug == "index":
        return base + "/"
    return f"{base}/{slug}"


async def retrieve_pages(
    conn,
    provider: EmbeddingProvider,
    query: str,
    top_k: int = 3,
    *,
    include_unapproved: bool = False,
) -> list[RetrievedPageChunk]:
    """Retrieval over the pages corpus (site_pages/page_chunks) -- a
    SEPARATE index from retrieve() above (see db.py's module docstring for
    why pages and PDFs are never mixed into one index).

    Deliberately NO recency cutoff: pages are the site's always-current
    content (unlike a dated internal-update PDF, a page has no "as of"
    date that can go stale in the same way) -- freshness is
    scripts/harvest_pages.py's job (re-run the harvester), not a serving-
    time filter. The WP-7c approval quarantine still applies: an
    unapproved/pending page's chunks are never eligible for a match, same
    `include_unapproved` escape hatch as retrieve() above.
    """
    from pubs_rag import db

    approved_only = Config.QUARANTINE_ENABLED and not include_unapproved

    [query_embedding] = provider.embed([query])
    rows = await db.search_page_chunks(conn, query_embedding, top_k, approved_only=approved_only)

    return [
        RetrievedPageChunk(
            content=row["content"],
            title=row["title"],
            slug=row["slug"],
            score=row["score"],
            page_url=page_url_for_slug(row["slug"]),
            captured_at=row["captured_at"],
        )
        for row in rows
    ]
