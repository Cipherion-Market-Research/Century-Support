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


def test_parses_all_publications_entries():
    html = (FIXTURES / "insights-and-publications.html").read_text()
    entries = parse_publication_index(html, listed_on=PUBLICATIONS_PAGE)
    assert {e["slug"] for e in entries} == _ok_pdf_slugs(PUBLICATIONS_PAGE)


def test_parses_all_updates_entries():
    html = (FIXTURES / "internal-updates.html").read_text()
    entries = parse_publication_index(html, listed_on=UPDATES_PAGE)
    assert {e["slug"] for e in entries} == _ok_pdf_slugs(UPDATES_PAGE)


def test_entry_fields_match_inventory():
    html = (FIXTURES / "insights-and-publications.html").read_text()
    entries = {e["slug"]: e for e in parse_publication_index(html, listed_on=PUBLICATIONS_PAGE)}
    inv = {e["slug"]: e for e in INVENTORY if e["kind"] == "pdf"}

    entry = entries["algorithmic-austerity"]
    assert entry["title"] == inv["algorithmic-austerity"]["title"]
    assert entry["date"] == inv["algorithmic-austerity"]["date"]
    assert entry["pdf_path"] == "/assets/documents/algorithmic-austerity.pdf"


# --- Corpus policy: ungated documents only (owner decision 2026-08-17, D-3) ---
# The tests above pin the parser's contract against the two real page
# fixtures via a live property (matches whatever inventory.json currently
# says should be ingestible for that page); the tests below pin the
# defensive gated-path check against the fixtures' exact, known-fixed
# content -- fine to hardcode, since fixtures don't grow.


def test_fixture_entries_unaffected_by_gated_path_check():
    """No regression: the two real index-page fixtures parse to exactly the
    same entries as before the gated-path defensive check was added, since
    none of their data-pdf values are gated/preview paths. This pins the
    fixtures' own fixed content, not the live corpus -- the fixture files
    only change when someone deliberately re-captures them."""
    pub_html = (FIXTURES / "insights-and-publications.html").read_text()
    pub_entries = parse_publication_index(pub_html, listed_on=PUBLICATIONS_PAGE)
    assert {e["slug"] for e in pub_entries} == {
        "genius-clarity-acts",
        "smart-contracts-in-commodity-futures-trading",
        "algorithmic-austerity",
        "rwa-tokenization",
    }
    assert all(e["pdf_path"].startswith("/assets/documents/") for e in pub_entries)

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
    """A real, publicly-resolvable PDF path is unaffected by the gated-path
    check -- same fields as a plain parse would have produced."""
    entries = parse_publication_index(_UNGATED_CARD_HTML, listed_on=PUBLICATIONS_PAGE)
    assert entries == [
        {
            "slug": "genius-clarity-acts",
            "title": "The GENIUS and CLARITY Acts",
            "date": "August 22, 2025",
            "pdf_path": "/assets/documents/genius-clarity-acts.pdf",
            "listed_on": PUBLICATIONS_PAGE,
        }
    ]


def test_gated_preview_pdf_path_is_skipped_and_logged(caplog):
    """Defensive backstop: an entry whose data-pdf points at a previews/
    teaser asset (the convention used for the gated documents' anonymously
    -harvestable first-page teasers -- see data/kb_source/inventory.json
    entries marked gated:true) must never be ingested, even if a future
    site change bakes it into static card markup. It is skipped and the
    skip is logged so the drop isn't silent."""
    with caplog.at_level("WARNING", logger="pubs_rag.site_parser"):
        entries = parse_publication_index(_GATED_TEASER_CARD_HTML, listed_on=PUBLICATIONS_PAGE)

    assert entries == []
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "2026-contribution-program" in message
    assert "previews/2026-contribution-program.pdf" in message
