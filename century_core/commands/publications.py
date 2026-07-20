"""/publications -- lists recent Ciphex publications from pubs_rag's
Postgres store. Reads the `documents` table directly (schema: sha256, kind,
slug, title, date, source_url, listed_on, ingested_at -- see
pubs_rag/db.py's DDL) rather than importing pubs_rag code, since this is a
read against a shared datastore, not a dependency on WP-4's internals.
Publication dates are free text (e.g. "April 15, 2026"), not ISO-8601, so
these are `links` items rather than `fact` blocks (C2's `fact.as_of` is
specified as ISO-8601).
"""
from century_core.models import HeadingBlock, LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta, WarningBlock

_LIST_QUERY = """
    SELECT title, date, source_url
    FROM documents
    WHERE kind = 'pdf'
    ORDER BY ingested_at DESC
    LIMIT $1
"""


async def handle_publications(args: str, stores) -> ResponseIR:
    blocks = [HeadingBlock(text="Ciphex Publications")]

    if stores.rag_conn is not None:
        rows = await stores.rag_conn.fetch(_LIST_QUERY, 5)
        if rows:
            blocks.append(ParagraphBlock(md="Recent publications:"))
            blocks.append(
                LinksBlock(
                    items=[
                        LinkItem(label=f"{row['title']} ({row['date']})", url=row["source_url"])
                        for row in rows
                    ]
                )
            )
        else:
            blocks.append(WarningBlock(md="No publications are indexed yet."))
    else:
        blocks.append(WarningBlock(md="The publications index is temporarily unavailable."))

    facts_used = []
    pub_link = stores.facts.get("links.ecosystem_publications")
    if pub_link is not None and not pub_link.is_unknown:
        blocks.append(LinksBlock(items=[LinkItem(label="All publications", url=str(pub_link.value))]))
        facts_used.append("links.ecosystem_publications")

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
