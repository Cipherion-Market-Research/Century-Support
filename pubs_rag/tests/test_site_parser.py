import json
from pathlib import Path

from pubs_rag.site_parser import parse_publication_index

FIXTURES = Path(__file__).parent / "fixtures"
KB_SOURCE = Path(__file__).resolve().parents[2] / "data" / "kb_source"
INVENTORY = json.loads((KB_SOURCE / "inventory.json").read_text())


def test_parses_all_publications_entries():
    html = (FIXTURES / "ecosystem-publications.html").read_text()
    entries = parse_publication_index(html, listed_on="ecosystem-publications")
    expected = {e["slug"] for e in INVENTORY if e.get("listed_on") == "ecosystem-publications"}
    assert {e["slug"] for e in entries} == expected


def test_parses_all_updates_entries():
    html = (FIXTURES / "ecosystem-updates.html").read_text()
    entries = parse_publication_index(html, listed_on="ecosystem-updates")
    expected = {e["slug"] for e in INVENTORY if e.get("listed_on") == "ecosystem-updates"}
    assert {e["slug"] for e in entries} == expected


def test_entry_fields_match_inventory():
    html = (FIXTURES / "ecosystem-publications.html").read_text()
    entries = {e["slug"]: e for e in parse_publication_index(html, listed_on="ecosystem-publications")}
    inv = {e["slug"]: e for e in INVENTORY if e["kind"] == "pdf"}

    entry = entries["algorithmic-austerity"]
    assert entry["title"] == inv["algorithmic-austerity"]["title"]
    assert entry["date"] == inv["algorithmic-austerity"]["date"]
    assert entry["pdf_path"] == "/assets/documents/algorithmic-austerity.pdf"
