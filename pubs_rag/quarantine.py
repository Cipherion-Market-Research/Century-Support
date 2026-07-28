"""Serving quarantine (WP-7c serving-safety hardening).

Every document row carries `approved: bool`. Documents ingested going
forward default `approved = FALSE` and must be explicitly approved (CLI:
`python -m pubs_rag.main approve <sha256-or-slug>`) before
`retrieval.retrieve()` will serve their chunks.

The original 12-document corpus (captured 2026-07-20, see
data/kb_source/inventory.json / pubs_rag/tests/test_ingest_and_retrieval.py)
is grandfathered approved=TRUE, via this EXPLICIT, HARDCODED sha256
allowlist -- deliberately not "every document currently sitting in the
documents table". That distinction matters: grandfathering by sha256 is
reproducible from a clean database (a fresh `ingest` run reconstructs the
exact same approval state every time), and it doesn't silently widen to
include whatever a given deployment's DB happens to hold at migration time.

A document's approval state is keyed off its own sha256, not "when it was
ingested" -- so this same list is what makes the superseded-slug case work
correctly for free: a re-used slug with genuinely new bytes gets a sha256
that is (by construction) not in this list, so the new version always
starts unapproved even though the slug itself is grandfathered.
"""

# fmt: off
GRANDFATHERED_SHA256 = frozenset({
    "d81cb03825264d79ed0dfeb9b67a4b8a828eafbbe78c4f7b480a7ba948832a55",  # 2026q1-optimization-results
    "19e16590e1c45379cf107ca18a364361e34a9de9cbcb6d3a5495c7392604b284",  # algorithmic-austerity
    "08969c96c724c1b3145d13034cebddb5f38d308c08bed1accc5fb37bc5cc9bbf",  # ecosystem-update-dec31-25
    "494fff14b0875cd30a6940b667d3c13463eb722992ef5635260496662765e091",  # ecosystem-update-feb16-26
    "a4e82e10e7cd0f9279f13df5a4a8bd82dae94cc04616fd938274d883e49e6bb4",  # ecosystem-update-feb27-26
    "cb794244b9b4ef49a71233a22d413c7977c475e6c0bb2f7ba4f3ecc0430ba2f8",  # ecosystem-update-jul22-25
    "724909184d8a30700cda8a376a1e09b39aca1ad838fd830c3212e000a70487ef",  # ecosystem-update-jul31-25
    "766990b6e89b450ead0cfca0ea683649a68a47a91efd90a265559cf087089d8a",  # ecosystem-update-may08-26
    "19f6a40514864c508a3bfe69d1a5c85cced2520d311cdd8dbbe595d2671bfe4d",  # fye-2025-ciphex-alpha-test-report-fnl
    "492f1235acf97019ed92752ef490676a7109f4cc6ac4e5c324172de62f9b8379",  # genius-clarity-acts
    "40428bb18cadb791f4a6315bbae3bddb38fa1662706ef1ecda70dbb237b441ac",  # rwa-tokenization
    "05787ffa34f1a63f3dc8ad2ce5b2949d99d84bae3d35228bdc4924320c02d869",  # smart-contracts-in-commodity-futures-trading
})
# fmt: on

assert len(GRANDFATHERED_SHA256) == 12, "grandfather list must match the 12 seeded corpus PDFs exactly"


def is_grandfathered(sha256: str) -> bool:
    return sha256 in GRANDFATHERED_SHA256


def looks_like_sha256(identifier: str) -> bool:
    """True if `identifier` is plausibly a full sha256 hex digest (64 hex
    chars), as opposed to a slug -- used by the approve/revoke CLI to
    decide which column to match on."""
    if len(identifier) != 64:
        return False
    try:
        int(identifier, 16)
    except ValueError:
        return False
    return True
