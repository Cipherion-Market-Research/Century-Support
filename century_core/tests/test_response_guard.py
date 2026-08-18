"""response_guard: brand-spelling normalization (defect 4, go-live incident
2026-08-17) and the existing structural final gate.
"""
from century_core import response_guard
from century_core.models import (
    FactBlock,
    HeadingBlock,
    LinkItem,
    LinksBlock,
    ParagraphBlock,
    ResponseIR,
    ResponseMeta,
    WarningBlock,
)


# ───────────────────────── normalize_brand_text ─────────────────────────


def test_normalizes_legacy_capital_x_spelling():
    assert response_guard.normalize_brand_text("The CipheX Alpha Network") == "The Ciphex Alpha Network"


def test_normalizes_all_caps_spelling():
    assert response_guard.normalize_brand_text("CIPHEX is great") == "Ciphex is great"


def test_normalizes_cipherx_variant():
    assert response_guard.normalize_brand_text("CipherX rocks") == "Ciphex rocks"


def test_normalizes_cipher_hyphen_x_variant():
    assert response_guard.normalize_brand_text("Cipher-X is old branding") == "Ciphex is old branding"


def test_canonical_spelling_is_idempotent():
    assert response_guard.normalize_brand_text("Ciphex is the brand.") == "Ciphex is the brand."
    assert response_guard.normalize_brand_text(response_guard.normalize_brand_text("CipheX")) == "Ciphex"


def test_does_not_touch_cipherion_legal_entity_name():
    text = "Cipherion Capital SA is the legal entity behind Ciphex."
    assert response_guard.normalize_brand_text(text) == text


def test_does_not_touch_url_containing_brand_spelling():
    text = "See https://CipheX.example.com/path for details."
    result = response_guard.normalize_brand_text(text)
    assert "https://CipheX.example.com/path" in result


def test_does_not_touch_email_address():
    text = "Email us at support@cipheX.io for help."
    result = response_guard.normalize_brand_text(text)
    assert "support@cipheX.io" in result


def test_normalizes_label_but_not_url_in_markdown_link():
    text = "See [CipheX Doc](https://ciphex.io/CipheX-doc) for details."
    result = response_guard.normalize_brand_text(text)
    assert "[Ciphex Doc](https://ciphex.io/CipheX-doc)" in result


def test_empty_text_passthrough():
    assert response_guard.normalize_brand_text("") == ""


# ───────────────────────── enforce_response applies normalization ─────────────────────────


def test_enforce_response_normalizes_paragraph_text():
    response = ResponseIR(
        blocks=[ParagraphBlock(md="The CipheX Alpha Network is CPX's ecosystem.")],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    paragraph = next(b for b in result.blocks if b.type == "paragraph")
    assert paragraph.md == "The Ciphex Alpha Network is CPX's ecosystem."


def test_enforce_response_normalizes_heading_and_warning_text():
    response = ResponseIR(
        blocks=[
            HeadingBlock(text="CIPHEX Overview"),
            WarningBlock(md="CipherX support is limited."),
        ],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    heading = next(b for b in result.blocks if b.type == "heading")
    warning = next(b for b in result.blocks if b.type == "warning")
    assert heading.text == "Ciphex Overview"
    assert warning.md == "Ciphex support is limited."


def test_enforce_response_normalizes_fact_label_and_value_but_not_source_url():
    response = ResponseIR(
        blocks=[
            FactBlock(
                label="CipheX Token Standard",
                value="ERC-20 on the CipheX network",
                source="https://ciphex.io/CipheX-legacy-path",
                as_of="2026-08-17",
            )
        ],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    fact = result.blocks[0]
    assert fact.label == "Ciphex Token Standard"
    assert fact.value == "ERC-20 on the Ciphex network"
    # .source is a URL field -- never rewritten.
    assert fact.source == "https://ciphex.io/CipheX-legacy-path"


def test_enforce_response_normalizes_link_label_but_not_url():
    response = ResponseIR(
        blocks=[
            LinksBlock(items=[LinkItem(label="CipheX Whitepaper", url="https://ciphex.io/CipheX-whitepaper.pdf")])
        ],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    item = result.blocks[0].items[0]
    assert item.label == "Ciphex Whitepaper"
    assert item.url == "https://ciphex.io/CipheX-whitepaper.pdf"


def test_enforce_response_preserves_cipherion_through_full_response():
    response = ResponseIR(
        blocks=[ParagraphBlock(md="Cipherion Capital SA operates the Ciphex ecosystem.")],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    paragraph = next(b for b in result.blocks if b.type == "paragraph")
    assert paragraph.md == "Cipherion Capital SA operates the Ciphex ecosystem."


def test_enforce_response_still_catches_guardrail_violations_after_normalization():
    response = ResponseIR(
        blocks=[ParagraphBlock(md="You should buy CipheX now, it's a great time to invest!")],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    assert result.meta.answer_kind == "refusal"


def test_safe_refusal_is_brand_clean():
    response = response_guard.safe_refusal()
    links = next(b for b in response.blocks if b.type == "links")
    assert links.items[0].label == "Ciphex"


# ───────────────── enforce_response: link allowlist (2026-08-18) ─────────────────
#
# Production audit, 2026-08-18: fact citations were rendering the literal
# string "internal://content-audit-2026-07-20" as an unclickable citation
# link, and RAG citations linked two now-404 PDF URLs. Final structural gate:
# any LinkItem whose url is not on Config.ALLOWED_LINK_PREFIXES is dropped.


def test_enforce_response_drops_link_with_non_allowlisted_url():
    response = ResponseIR(
        blocks=[
            LinksBlock(
                items=[
                    LinkItem(label="Content audit", url="internal://content-audit-2026-07-20"),
                    LinkItem(label="Ciphex", url="https://ciphex.io"),
                ]
            )
        ],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    links = next(b for b in result.blocks if b.type == "links")
    urls = {item.url for item in links.items}
    assert urls == {"https://ciphex.io"}


def test_enforce_response_drops_basescan_link():
    # basescan.org is deliberately NOT allowlisted -- Base is never
    # presented as a legitimate CPX deployment.
    response = ResponseIR(
        blocks=[
            LinksBlock(
                items=[
                    LinkItem(label="Basescan", url="https://basescan.org/token/0xdead"),
                    LinkItem(label="Ciphex", url="https://ciphex.io"),
                ]
            )
        ],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    links = next(b for b in result.blocks if b.type == "links")
    assert {item.url for item in links.items} == {"https://ciphex.io"}


def test_enforce_response_drops_old_presale_domain_link():
    # presale.ciphex.io is deliberately NOT allowlisted ("presale" is
    # banned vocabulary with no exemptions -- see BLOCKED_FACT_KEYS's
    # links.claim_portal_legacy_redirect). Label avoids the banned word
    # itself so this test isolates the link-allowlist behavior from the
    # separate text-guardrail check.
    response = ResponseIR(
        blocks=[
            LinksBlock(
                items=[
                    LinkItem(label="Old claim portal", url="https://presale.ciphex.io"),
                    LinkItem(label="Ciphex", url="https://ciphex.io"),
                ]
            )
        ],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    links = next(b for b in result.blocks if b.type == "links")
    assert {item.url for item in links.items} == {"https://ciphex.io"}


def test_enforce_response_removes_links_block_left_empty_after_filtering():
    response = ResponseIR(
        blocks=[
            ParagraphBlock(md="Some answer text."),
            LinksBlock(items=[LinkItem(label="Bad", url="internal://not-a-real-url")]),
        ],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    assert not any(b.type == "links" for b in result.blocks)
    assert any(b.type == "paragraph" for b in result.blocks)


def test_enforce_response_keeps_all_allowlisted_links_untouched():
    urls = [
        "https://ciphex.io/contribute",
        "https://claim.ciphex.io",
        "https://ams.ciphex.io",
        "https://connect.ciphex.io",
        "https://t.me/ciphexgroup",
        "https://x.com/ciphexio",
        "https://skynet.certik.com/projects/ciphex",
        "https://etherscan.io/token/0x18b33687d1c804Dd4ea6c82106e54923c23a652E",
        "https://etherscan.io/address/0x18b33687d1c804Dd4ea6c82106e54923c23a652E",
        "https://etherscan.io/address/0x28995579fdf4F1Ea01ba54b6F4f0524cE63Ff1bc",
    ]
    response = ResponseIR(
        blocks=[LinksBlock(items=[LinkItem(label=f"link {i}", url=u) for i, u in enumerate(urls)])],
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
    result = response_guard.enforce_response(response)
    links = next(b for b in result.blocks if b.type == "links")
    assert {item.url for item in links.items} == set(urls)
