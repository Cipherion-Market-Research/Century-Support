import json
from pathlib import Path

import pytest

from pubs_rag.pdf_extract import extract_pdf_text

KB_SOURCE = Path(__file__).resolve().parents[2] / "data" / "kb_source"
INVENTORY = json.loads((KB_SOURCE / "inventory.json").read_text())
PDF_ENTRIES = [e for e in INVENTORY if e["kind"] == "pdf"]


def test_inventory_has_all_twelve_pdfs():
    assert len(PDF_ENTRIES) == 12


@pytest.mark.parametrize("entry", PDF_ENTRIES, ids=[e["slug"] for e in PDF_ENTRIES])
def test_decrypts_and_extracts_each_real_pdf(entry):
    path = KB_SOURCE / "pdfs" / f"{entry['slug']}.pdf"
    extracted = extract_pdf_text(str(path))
    assert extracted.page_count == entry["pdf_pages"]
    assert len(extracted.text.split()) > 0


def test_extract_from_bytes_matches_extract_from_path():
    entry = PDF_ENTRIES[0]
    path = KB_SOURCE / "pdfs" / f"{entry['slug']}.pdf"
    from_path = extract_pdf_text(str(path))
    from_bytes = extract_pdf_text(path.read_bytes())
    assert from_path.text == from_bytes.text
    assert from_path.page_count == from_bytes.page_count


def test_burn_content_lives_in_algorithmic_austerity():
    entry = next(e for e in PDF_ENTRIES if e["slug"] == "algorithmic-austerity")
    path = KB_SOURCE / "pdfs" / f"{entry['slug']}.pdf"
    text = extract_pdf_text(str(path)).text.lower()
    assert text.count("burn") >= 5
