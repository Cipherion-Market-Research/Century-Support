"""/updates -- lists recent Ciphex Internal Updates (announcements &
official press releases) from pubs_rag's Postgres store. Reads the
`documents` table directly (schema: sha256, kind, slug, title, date,
source_url, listed_on, ingested_at -- see pubs_rag/db.py's DDL) rather than
importing pubs_rag code, since this is a read against a shared datastore,
not a dependency on WP-4's internals. Update dates are free text (e.g.
"April 15, 2026"), not ISO-8601, so these are `links` items rather than
`fact` blocks (C2's `fact.as_of` is specified as ISO-8601).

Replaces the former /publications command (removed 2026-08-18). Per the
approved "Telegram & GitHub Bot Parameter Requirements": the bot's only
approved knowledge sources are the main website crawl and Internal Updates
-- the entire Insights & Publications section is excluded (never indexed,
retrieved, referenced, quoted, or summarized; see config.Config.
BLOCKED_FACT_KEYS and pubs_rag/config.py's SERVE_INSIGHTS_AND_PUBLICATIONS).
This handler therefore only ever lists rows with listed_on =
'internal-updates' (the ecosystem-update-* documents on
ciphex.io/internal-updates) -- filtering on that column, not a slug prefix,
so it stays correct even if a future document's slug doesn't happen to
start with "ecosystem-update-".

WP-7c serving quarantine: `documents.approved` gates whether a document is
eligible for a user-facing answer -- pubs_rag/retrieval.py's retrieve()
respects this (approved-only by default; see pubs_rag/db.py's DDL and
quarantine.py). This query mirrors that: `approved = TRUE` so a
newly-webhook-ingested, not-yet-reviewed document never appears here before
an admin has approved it, the same guarantee RAG citations already have.

Serving recency cutoff (positioning-freshness policy, owner feedback
2026-08-19): a SEPARATE gate from `approved` above -- see
pubs_rag/config.py's Config.SERVE_DOCS_SINCE for the full rationale (live
testers caught the bot citing pre-rebrand 2025-era updates as if current).
/updates must give the same freshness guarantee pubs_rag/retrieval.py's
retrieve() does: a reviewed-and-approved-but-stale update must never be
listed either. This mirrors PUBS_RAG_SERVE_DOCS_SINCE (same env var name
and default) rather than importing pubs_rag.config, for the same
zero-coupling reason as the rest of this module -- both reads are just
"the same env var, read independently," not a shared code dependency.
`documents.date` is free text ("July 25, 2026"), not a real date column
(see pubs_rag/db.py's DDL), so -- like pubs_rag/date_utils.py -- the
comparison happens in Python after an oversampled fetch, not as a SQL WHERE
clause that could throw on an unexpected date string.

Tester feedback (2026-08-19): each listed entry must show its title, its
date, and a link to that specific document's PDF (not a generic link) --
the "All updates" link below is the only non-specific link in this
response. No machine-generated content summaries are added here (brand
copy/tone approval for that is still pending with the owner).
"""
import logging
import os
from datetime import datetime

from century_core.models import HeadingBlock, LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta, WarningBlock

logger = logging.getLogger(__name__)

# Same env var, same default as pubs_rag.config.Config.SERVE_DOCS_SINCE --
# see this module's docstring for why it's re-read here rather than
# imported. Read at import time (like every other env-driven constant in
# this codebase): a changed value takes effect on the next process
# restart/redeploy, not live against an already-running process.
_SERVE_DOCS_SINCE = os.environ.get("PUBS_RAG_SERVE_DOCS_SINCE", "2026-05-01")

# Same format list as pubs_rag/date_utils.py -- kept in sync manually since
# this module deliberately doesn't import pubs_rag code (see docstring).
_DATE_FORMATS = ("%B %d, %Y", "%Y-%m-%d")

_logged_unparseable_titles: set[str] = set()

_LIST_QUERY = """
    SELECT title, date, source_url
    FROM documents
    WHERE kind = 'pdf' AND listed_on = 'internal-updates' AND approved = TRUE
    ORDER BY ingested_at DESC
    LIMIT $1
"""

# Rows shown to the user (after the recency filter narrows the candidates
# below). The fetch limit is deliberately larger: filtering out stale rows
# from a too-small candidate pool could leave fewer than _DISPLAY_LIMIT
# entries even when enough fresh ones exist further back in ingested_at
# order.
_DISPLAY_LIMIT = 5
_FETCH_LIMIT = 50


def _parse_document_date(raw):
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_cutoff(raw):
    if not raw:
        return None
    return datetime.strptime(raw.strip(), "%Y-%m-%d").date()


def _passes_recency_cutoff(row, cutoff) -> bool:
    doc_date = _parse_document_date(row["date"])
    if doc_date is None:
        title = row["title"]
        if title not in _logged_unparseable_titles:
            _logged_unparseable_titles.add(title)
            logger.warning(
                "/updates: excluding document title=%r (date=%r) -- date is missing or "
                "unparseable, and the serving recency cutoff (%s) treats that "
                "conservatively as excluded rather than guessing it's current",
                title,
                row["date"],
                _SERVE_DOCS_SINCE,
            )
        return False
    return doc_date >= cutoff


async def handle_updates(args: str, stores) -> ResponseIR:
    blocks = [HeadingBlock(text="Ciphex Announcements & Updates")]

    if stores.rag_conn is not None:
        rows = await stores.rag_conn.fetch(_LIST_QUERY, _FETCH_LIMIT)
        cutoff = _parse_cutoff(_SERVE_DOCS_SINCE)
        if cutoff is not None:
            rows = [row for row in rows if _passes_recency_cutoff(row, cutoff)]
        rows = rows[:_DISPLAY_LIMIT]

        if rows:
            blocks.append(ParagraphBlock(md="Recent internal updates:"))
            blocks.append(
                LinksBlock(
                    items=[
                        LinkItem(label=f"{row['title']} — {row['date']}", url=row["source_url"])
                        for row in rows
                    ]
                )
            )
        else:
            blocks.append(WarningBlock(md="No updates are indexed yet."))
    else:
        blocks.append(WarningBlock(md="The updates index is temporarily unavailable."))

    facts_used = []
    updates_link = stores.facts.get("links.ecosystem_updates")
    if updates_link is not None and not updates_link.is_unknown:
        blocks.append(LinksBlock(items=[LinkItem(label="All updates", url=str(updates_link.value))]))
        facts_used.append("links.ecosystem_updates")

    blocks.append(
        ParagraphBlock(md="Related: /ecosystem — products overview · /contribute — Contribution Program")
    )

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
