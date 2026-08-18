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
"""
from century_core.models import HeadingBlock, LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta, WarningBlock

_LIST_QUERY = """
    SELECT title, date, source_url
    FROM documents
    WHERE kind = 'pdf' AND listed_on = 'internal-updates' AND approved = TRUE
    ORDER BY ingested_at DESC
    LIMIT $1
"""


async def handle_updates(args: str, stores) -> ResponseIR:
    blocks = [HeadingBlock(text="Ciphex Announcements & Updates")]

    if stores.rag_conn is not None:
        rows = await stores.rag_conn.fetch(_LIST_QUERY, 5)
        if rows:
            blocks.append(ParagraphBlock(md="Recent internal updates:"))
            blocks.append(
                LinksBlock(
                    items=[
                        LinkItem(label=f"{row['title']} ({row['date']})", url=row["source_url"])
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

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
