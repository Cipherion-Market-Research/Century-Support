"""Idempotent ingestion: sha256-keyed dedup -> chunk -> embed -> upsert.

Scope: PDFs only ("Publications ingestion (RAG)" — WP-4). The corpus'
18 general site pages are deliberately excluded: they're WP-2's territory
(facts.yaml, canonical structured facts extracted from page copy), and
mixing them into this RAG index causes exact-phrase page content (e.g.
ciphex-token.md's "Burn Cycle" stats table) to outrank the actual
publications discussing the same topic in prose. The two publication index
pages are still read by this package (site_parser.py) but only for their
structural data-slug/data-title/data-date/data-pdf metadata, never as
retrievable chunk text.

Two entry points:
  - ingest_document(): the core primitive, given already-extracted text and
    metadata for one document. Used by both the initial corpus load and the
    webhook-triggered refresh path (webhook.py), so both share one
    idempotency rule.
  - ingest_inventory(): walks data/kb_source/inventory.json (the initial
    seed corpus) and calls ingest_document() for every PDF.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from pubs_rag import db
from pubs_rag.chunking import chunk_text
from pubs_rag.config import Config
from pubs_rag.embeddings import EmbeddingProvider
from pubs_rag.pdf_extract import extract_pdf_text
from pubs_rag.quarantine import is_grandfathered

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    slug: str
    sha256: str
    skipped: bool
    superseded: bool
    chunk_count: int


@dataclass
class IngestSummary:
    results: list[IngestResult]

    @property
    def ingested(self) -> int:
        return sum(1 for r in self.results if not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    @property
    def superseded(self) -> int:
        return sum(1 for r in self.results if r.superseded)


async def ingest_document(conn, provider: EmbeddingProvider, doc_meta: dict, raw_text: str) -> IngestResult:
    slug = doc_meta["slug"]
    sha256 = doc_meta["sha256"]

    existing_sha = await db.get_document_sha_by_slug(conn, slug)
    if existing_sha == sha256:
        return IngestResult(slug=slug, sha256=sha256, skipped=True, superseded=False, chunk_count=0)

    chunks = chunk_text(raw_text, Config.CHUNK_SIZE_WORDS, Config.CHUNK_OVERLAP_WORDS)
    embeddings = provider.embed(chunks) if chunks else []

    superseded = existing_sha is not None and existing_sha != sha256
    # WP-7c serving quarantine: approval is keyed off the document's own
    # sha256 (an explicit, deterministic allowlist -- see quarantine.py),
    # never off "when it was ingested". This is what makes a superseded doc
    # correctly land unapproved even though its slug was grandfathered: new
    # bytes -> a new sha256 that (by construction) isn't in the allowlist.
    approved = is_grandfathered(sha256)
    tx = conn.transaction()
    await tx.start()
    try:
        if superseded:
            await db.delete_document(conn, existing_sha)
        await db.upsert_document(
            conn,
            sha256=sha256,
            kind=doc_meta["kind"],
            slug=slug,
            title=doc_meta["title"],
            date=doc_meta.get("date"),
            source_url=doc_meta["source_url"],
            listed_on=doc_meta.get("listed_on"),
            approved=approved,
        )
        await db.insert_chunks(conn, sha256, chunks, embeddings)
    except Exception:
        await tx.rollback()
        raise
    else:
        await tx.commit()

    return IngestResult(slug=slug, sha256=sha256, skipped=False, superseded=superseded, chunk_count=len(chunks))


def _load_pdf_text(entry: dict, kb_source_dir: Path) -> str:
    path = kb_source_dir / "pdfs" / f"{entry['slug']}.pdf"
    return extract_pdf_text(str(path)).text


async def ingest_inventory(conn, provider: EmbeddingProvider, kb_source_dir: str = None) -> IngestSummary:
    kb_dir = Path(kb_source_dir or Config.KB_SOURCE_DIR)
    inventory = json.loads((kb_dir / "inventory.json").read_text(encoding="utf-8"))

    results = []
    for entry in inventory:
        if entry["kind"] != "pdf":
            continue
        if entry.get("extraction") != "ok":
            logger.warning("skipping %s: extraction status %r", entry["slug"], entry.get("extraction"))
            continue

        raw_text = _load_pdf_text(entry, kb_dir)

        doc_meta = {
            "sha256": entry["sha256"],
            "kind": entry["kind"],
            "slug": entry["slug"],
            "title": entry["title"],
            "date": entry.get("date"),
            "source_url": entry["source_url"],
            "listed_on": entry.get("listed_on"),
        }
        result = await ingest_document(conn, provider, doc_meta, raw_text)
        logger.info(
            "%s: %s", entry["slug"], "skipped (unchanged)" if result.skipped else f"ingested ({result.chunk_count} chunks)"
        )
        results.append(result)

    return IngestSummary(results=results)
