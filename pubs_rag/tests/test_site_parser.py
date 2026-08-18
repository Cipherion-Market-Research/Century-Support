import json
from pathlib import Path

from pubs_rag.site_parser import parse_publication_index

FIXTURES = Path(__file__).parent / "fixtures"
KB_SOURCE = Path(__file__).resolve().parents[2] / "data" / "kb_source"
INVENTORY = json.loads((KB_SOURCE / "inventory.json").read_text())

# Real page identifiers -- matches Config.PUBLICATION_INDEX_PATHS's stems
# (see pubs_rag/config.py) and the `listed_on` values inventory.json's
# harvester actually stamps on each PDF entry today. These have already
# been renamed once (ecosystem-publications -> insights-and-publications,
# ecosystem-updates -> internal-updates, 2026-07-28); the fixtures below are
# named to match.
PUBLICATIONS_PAGE = "insights-and-publications"
UPDATES_PAGE = "internal-updates"

# The gated-path defensive check (SERVE_GATED_DOCUMENTS, D-3) is orthogonal
# to the page-level Insights & Publications exclusion (SERVE_INSIGHTS_AND_
# PUBLICATIONS, Bot Parameter Requirements 2026-08-18) -- these snippets are
# listed_on=UPDATES_PAGE (an approved page) so they exercise the gated-path
# check in isolation, without the page-level exclusion short-circuiting them
# first.
_UNGATED_CARD_HTML = """
<div class="pub-grid">
  <button type="button" class="pdf-preview-card"
    data-slug="genius-clarity-acts"
    data-title="The GENIUS and CLARITY Acts"
    data-date="August 22, 2025"
    data-pdf="/assets/documents/genius-clarity-acts.pdf">
  </button>
</div>
"""

_GATED_TEASER_CARD_HTML = """
<div class="pub-grid">
  <button type="button" class="pdf-preview-card"
    data-slug="2026-contribution-program"
    data-title="2026 Contribution Program"
    data-date="July 20, 2026"
    data-pdf="/assets/documents/previews/2026-contribution-program.pdf">
  </button>
</div>
"""


def _ok_pdf_slugs(listed_on: str) -> set:
    """Every PDF the pipeline actually intends to ingest for a given page --
    extraction=="ok" only, since gated/preview entries are never expected to
    have static card markup (see site_parser.py's module docstring). Not a
    frozen count: recomputed from whatever inventory.json currently lists."""
    return {
        e["slug"]
        for e in INVENTORY
        if e["kind"] == "pdf" and e.get("listed_on") == listed_on and e.get("extraction") == "ok"
    }


# --- Corpus policy: approved sources are the main site crawl + Internal ---
# --- Updates only; the entire Insights & Publications section is        ---
# --- excluded (Bot Parameter Requirements, 2026-08-18)                  ---
#
# This supersedes the earlier "ungated-only" policy (D-3, 2026-08-17): even
# the small set of public "Legacy Contributor Publications" PDFs that used
# to pass the gated-path check are now excluded outright, because they're
# listed on the excluded page -- not because of anything about their PDF
# path. The assertions below derive "excluded" from the entry's listed_on,
# the same live property pattern as _ok_pdf_slugs above, never a hardcoded
# slug list.


def test_publications_page_entries_are_all_excluded():
    """No entry listed on the Insights & Publications page may ever be
    ingested, regardless of how many the page lists or what inventory.json
    currently records for it -- the page itself is not an approved source."""
    html = (FIXTURES / "insights-and-publications.html").read_text()
    entries = parse_publication_index(html, listed_on=PUBLICATIONS_PAGE)
    assert entries == []


def test_publications_page_exclusion_is_logged(caplog):
    """The exclusion is a warning, not a silent drop -- one per skipped
    card, naming the slug so a drop is traceable in logs."""
    html = (FIXTURES / "insights-and-publications.html").read_text()
    with caplog.at_level("WARNING", logger="pubs_rag.site_parser"):
        entries = parse_publication_index(html, listed_on=PUBLICATIONS_PAGE)

    assert entries == []
    assert len(caplog.records) > 0
    assert all("Insights & Publications" in r.getMessage() for r in caplog.records)


def test_parses_all_updates_entries():
    html = (FIXTURES / "internal-updates.html").read_text()
    entries = parse_publication_index(html, listed_on=UPDATES_PAGE)
    assert {e["slug"] for e in entries} == _ok_pdf_slugs(UPDATES_PAGE)


def test_entry_fields_match_inventory():
    html = (FIXTURES / "internal-updates.html").read_text()
    entries = {e["slug"]: e for e in parse_publication_index(html, listed_on=UPDATES_PAGE)}
    inv = {e["slug"]: e for e in INVENTORY if e["kind"] == "pdf"}

    entry = entries["ecosystem-update-jul22-25"]
    assert entry["title"] == inv["ecosystem-update-jul22-25"]["title"]
    assert entry["date"] == inv["ecosystem-update-jul22-25"]["date"]
    assert entry["pdf_path"] == "/assets/documents/ecosystem-update-jul22-25.pdf"


# --- Corpus policy: gated-path defensive check (owner decision 2026-08-17, D-3) ---
# The tests above pin the parser's contract against the two real page
# fixtures via live properties (matches whatever inventory.json/the page
# exclusion currently says should be ingestible); the tests below pin the
# defensive gated-path check against the fixtures' exact, known-fixed
# content -- fine to hardcode, since fixtures don't grow.


def test_fixture_entries_unaffected_by_gated_path_check():
    """No regression: the internal-updates page fixture parses to exactly
    the same entries as before the gated-path defensive check was added,
    since none of its data-pdf values are gated/preview paths. (The
    insights-and-publications fixture is covered by the page-exclusion
    tests above -- none of its entries reach the gated-path check at all.)"""
    updates_html = (FIXTURES / "internal-updates.html").read_text()
    updates_entries = parse_publication_index(updates_html, listed_on=UPDATES_PAGE)
    assert {e["slug"] for e in updates_entries} == {
        "ecosystem-update-jul25-26",
        "ecosystem-update-may08-26",
        "ecosystem-update-feb27-26",
        "ecosystem-update-feb16-26",
        "ecosystem-update-dec31-25",
        "ecosystem-update-jul31-25",
        "ecosystem-update-jul22-25",
    }
    assert all(e["pdf_path"].startswith("/assets/documents/") for e in updates_entries)


def test_ungated_card_parses_unchanged():
    """A real, publicly-resolvable PDF path on an approved page is
    unaffected by the gated-path check -- same fields as a plain parse
    would have produced."""
    entries = parse_publication_index(_UNGATED_CARD_HTML, listed_on=UPDATES_PAGE)
    assert entries == [
        {
            "slug": "genius-clarity-acts",
            "title": "The GENIUS and CLARITY Acts",
            "date": "August 22, 2025",
            "pdf_path": "/assets/documents/genius-clarity-acts.pdf",
            "listed_on": UPDATES_PAGE,
        }
    ]


def test_gated_preview_pdf_path_is_skipped_and_logged(caplog):
    """Defensive backstop: an entry whose data-pdf points at a previews/
    teaser asset (the convention used for the gated documents' anonymously
    -harvestable first-page teasers -- see data/kb_source/inventory.json
    entries marked gated:true) must never be ingested, even on an approved
    page, even if a future site change bakes it into static card markup. It
    is skipped and the skip is logged so the drop isn't silent."""
    with caplog.at_level("WARNING", logger="pubs_rag.site_parser"):
        entries = parse_publication_index(_GATED_TEASER_CARD_HTML, listed_on=UPDATES_PAGE)

    assert entries == []
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "2026-contribution-program" in message
    assert "previews/2026-contribution-program.pdf" in message
