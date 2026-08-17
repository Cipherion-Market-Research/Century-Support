import json
from pathlib import Path

import pytest

from pubs_rag.pdf_extract import extract_pdf_text

REPO_ROOT = Path(__file__).resolve().parents[2]
KB_SOURCE = REPO_ROOT / "data" / "kb_source"
INVENTORY = json.loads((KB_SOURCE / "inventory.json").read_text())
PDF_ENTRIES = [e for e in INVENTORY if e["kind"] == "pdf"]

# The corpus is open-ended (new PDFs land continuously via the webhook --
# see ingest.py), so nothing here may pin an exact count or a hardcoded
# slug list. Instead we discover, at collection time, whatever inventory.json
# currently lists and partition it the same way ingest_inventory() does:
# extraction=="ok" entries get fully parametrized over; everything else
# (gated/preview teasers) is asserted to be excluded, not failed.
OK_PDF_ENTRIES = [e for e in PDF_ENTRIES if e.get("extraction") == "ok"]
NON_OK_PDF_ENTRIES = [e for e in PDF_ENTRIES if e.get("extraction") != "ok"]


def _path_for(entry: dict) -> Path:
    # inventory.json's local_path is the source of truth for on-disk
    # location -- it already accounts for the preview-<slug>.pdf naming
    # convention used by gated entries, where the filename does not match
    # the slug. Never reconstruct the filename from the slug (that's the
    # bug this fixes: see the identical mistake ingest._load_pdf_text
    # avoids by only ever being called for extraction=="ok" entries, whose
    # filenames do match their slugs).
    return REPO_ROOT / entry["local_path"]


def test_inventory_pdf_entries_partition_cleanly_into_ok_and_gated():
    """Doesn't pin a count -- the corpus grows forever -- but pins the
    *shape* every PDF entry must have: cleanly extracted (extraction ==
    "ok", handled below) or explicitly gated/preview (also handled below,
    but excluded from full-text extraction). There must be at least one
    "ok" entry or every parametrized test below is vacuously skipped."""
    assert OK_PDF_ENTRIES, "inventory has no extraction==ok PDFs -- nothing to test extraction against"
    assert len(OK_PDF_ENTRIES) + len(NON_OK_PDF_ENTRIES) == len(PDF_ENTRIES)


def test_every_ok_entry_has_a_readable_file_matching_its_sha256():
    """Property that must hold for every entry ingest_inventory() will
    actually ingest, regardless of how many there are or what they're
    called: the file it points at exists, is readable, and its bytes match
    the sha256 recorded in the inventory (the same hash quarantine.py keys
    approval off of)."""
    import hashlib

    for entry in OK_PDF_ENTRIES:
        path = _path_for(entry)
        assert path.is_file(), f"{entry['slug']}: {path} does not exist"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == entry["sha256"], f"{entry['slug']}: on-disk sha256 does not match inventory"


def test_gated_entries_are_excluded_from_ingestion_and_never_look_like_full_documents():
    """Corpus policy: an entry whose extraction isn't "ok" (gated/preview --
    see inventory.json `gated: true` teaser entries, only a first-page
    image with no text layer) must never be treated as a full document.
    ingest_inventory() enforces this by skipping anything whose extraction
    isn't "ok" before it ever builds a filesystem path; this test pins the
    structural fact that makes naive slug-based path construction unsafe in
    the first place -- the on-disk filename for a gated entry does not
    equal `{slug}.pdf`, so it can never be silently picked up as if it were
    the real, full document."""
    assert NON_OK_PDF_ENTRIES, (
        "no gated/preview entries in inventory -- if the corpus policy changed, "
        "this test (and the gated-path checks in site_parser) need revisiting"
    )
    for entry in NON_OK_PDF_ENTRIES:
        path = _path_for(entry)
        assert path.is_file(), f"{entry['slug']}: {path} does not exist"
        assert path.name != f"{entry['slug']}.pdf", (
            f"{entry['slug']}: gated entry's on-disk filename matches its slug exactly -- "
            "naive slug-based path construction would wrongly resolve to it as a full document"
        )


@pytest.mark.parametrize("entry", OK_PDF_ENTRIES, ids=[e["slug"] for e in OK_PDF_ENTRIES])
def test_decrypts_and_extracts_each_real_pdf(entry):
    path = _path_for(entry)
    extracted = extract_pdf_text(str(path))
    assert extracted.page_count == entry["pdf_pages"]
    assert len(extracted.text.split()) > 0


def test_extract_from_bytes_matches_extract_from_path():
    entry = OK_PDF_ENTRIES[0]
    path = _path_for(entry)
    from_path = extract_pdf_text(str(path))
    from_bytes = extract_pdf_text(path.read_bytes())
    assert from_path.text == from_bytes.text
    assert from_path.page_count == from_bytes.page_count


def test_burn_content_lives_in_algorithmic_austerity():
    entry = next((e for e in OK_PDF_ENTRIES if e["slug"] == "algorithmic-austerity"), None)
    if entry is None:
        pytest.skip("algorithmic-austerity is not in the current ok-extraction corpus")
    path = _path_for(entry)
    text = extract_pdf_text(str(path)).text.lower()
    assert text.count("burn") >= 5
