"""Parse the two publication index pages from the ciphex-website source.

ciphex.io is a client-rendered Vite SPA for most routes (no content API —
see the ecosystem map), but `/ecosystem-publications` and
`/ecosystem-updates` are each backed by their own static, server-rendered
HTML entry file in the ciphex-website repo (`src/ecosystem-publications.html`,
`src/ecosystem-updates.html`, confirmed against Cipherion-Market-Research/
ciphex-website@main). Each publication is a `.pdf-preview-card` button
carrying `data-slug` / `data-title` / `data-date` / `data-pdf` attributes
baked in at build time — so a plain GitHub raw-content fetch + BeautifulSoup
parse gets the same metadata a headless browser would get from the live
site, with no JS rendering required.

Corpus policy (owner decision 2026-08-17, D-3; see config.Config.
SERVE_GATED_DOCUMENTS): this parser must only ever yield ungated,
publicly-resolvable documents. As of the 2026-07-28 insights-and-publications
restructure, ciphex.io's wallet-gated (SIWE) document library is rendered
client-side from `GET /api/library` after wallet sign-in and never appears
as `.pdf-preview-card` markup in the server-rendered HTML this parser reads
-- only the small "Legacy Contributor Publications" set still ships that
way, with a real `/assets/documents/...` PDF path. So there is currently no
gating attribute on the card markup itself to filter on. `_is_public_pdf_path`
below is a defensive backstop, not a response to markup that exists today:
if a future site change ever bakes a gated entry into static card markup
(e.g. with a teaser/preview asset in `data-pdf` instead of the real PDF),
this still refuses to ingest it, skipping and logging instead.
"""
import logging
from pathlib import PurePosixPath

from bs4 import BeautifulSoup

from pubs_rag.config import Config

logger = logging.getLogger(__name__)


def _is_public_pdf_path(pdf_path: str) -> bool:
    """True if `pdf_path` looks like a real, publicly-resolvable PDF asset
    rather than a gated teaser/preview. Rejects an empty/missing path and
    any path with a `previews` segment (the naming convention used for the
    anonymously-harvestable first-page teaser images of the gated
    documents -- see data/kb_source/inventory.json entries marked
    gated:true, e.g. `preview-<slug>.pdf`)."""
    if not pdf_path:
        return False
    return "previews" not in PurePosixPath(pdf_path).parts


def parse_publication_index(html: str, listed_on: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for card in soup.select(".pdf-preview-card[data-slug]"):
        slug = card["data-slug"]
        pdf_path = card.get("data-pdf", "")

        if not Config.SERVE_GATED_DOCUMENTS and not _is_public_pdf_path(pdf_path):
            logger.warning(
                "site_parser: skipping slug=%r (listed_on=%r) -- pdf_path %r is not a "
                "resolvable public PDF; corpus policy serves ungated documents only "
                "(config.Config.SERVE_GATED_DOCUMENTS)",
                slug,
                listed_on,
                pdf_path,
            )
            continue

        entries.append(
            {
                "slug": slug,
                "title": card["data-title"],
                "date": card["data-date"],
                "pdf_path": pdf_path,
                "listed_on": listed_on,
            }
        )
    return entries
