"""Q&A router: deterministic supply path, facts-only path, RAG path
(mocked pubs_rag.retrieval.retrieve), and guardrail-triggered fallbacks.
"""
import pytest
from dataclasses import dataclass

from century_core.qa.holders import is_holder_question
from century_core.qa.labels import humanize_fact_key
from century_core.qa.offtopic import is_offtopic_question
from century_core.qa.price import is_price_question
from century_core.qa.router import answer_question
from century_core.qa.supply import is_supply_question


# ─────────────────────────── supply distinction ───────────────────────────


def test_is_supply_question_triggers_on_keyword():
    assert is_supply_question("what is the total supply of CPX?")
    assert is_supply_question("how much circulating supply is there")
    assert not is_supply_question("what is the claim portal URL")


def test_is_supply_question_triggers_on_burn_phrasing():
    assert is_supply_question("how many tokens were burned?")
    assert is_supply_question("tell me about the burn")
    assert is_supply_question("what got burned in Burn Cycle 1?")


async def test_burn_question_routes_to_deterministic_supply_path(stub_stores):
    response = await answer_question("how many CPX tokens have been burned?", stub_stores)
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    labels = {b.label for b in fact_blocks}
    assert "On-chain totalSupply() (Ethereum)" in labels
    assert "Effective supply (post Burn Cycle 1)" in labels


# ─────────────────────────── price-intent detection ───────────────────────────


def test_is_price_question_triggers_on_keyword():
    assert is_price_question("what is the price of CPX?")
    assert is_price_question("how much does CPX cost")
    assert is_price_question("what is CPX worth")
    assert is_price_question("how much is CPX")


def test_is_price_question_conservative_does_not_swallow_supply_questions():
    assert not is_price_question("what is the total supply of CPX?")
    assert not is_price_question("how much circulating supply is there")
    assert not is_price_question("how many tokens were burned")


def test_is_price_question_conservative_does_not_swallow_unrelated_questions():
    assert not is_price_question("where can I claim my tokens?")
    assert not is_price_question("what chain is CPX on?")


async def test_price_question_routes_to_deterministic_price_command(stub_stores):
    response = await answer_question("what is the price of CPX?", stub_stores)
    assert response.meta.answer_kind == "command"
    heading = next(b for b in response.blocks if b.type == "heading")
    assert heading.text == "CPX Price"


async def test_price_question_checked_after_supply_so_supply_wins_on_overlap(stub_stores):
    # A query containing both "supply" and "cost"-adjacent words must still
    # go to the supply path, never the price path -- is_supply_question is
    # checked first in the router.
    response = await answer_question("what is the total supply worth right now?", stub_stores)
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    labels = {b.label for b in fact_blocks}
    assert "On-chain totalSupply() (Ethereum)" in labels


async def test_supply_question_distinguishes_onchain_from_effective_via_facts_fallback(stub_stores):
    # No KPI seeded -> falls back to facts.yaml, which itself carries both
    # figures distinctly (tokenomics.onchain_total_supply_eth vs fy2026_fd_supply).
    response = await answer_question("what is the total supply of CPX?", stub_stores)

    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    labels = {b.label for b in fact_blocks}
    assert "On-chain totalSupply() (Ethereum)" in labels
    assert "Effective supply (post Burn Cycle 1)" in labels

    onchain = next(b for b in fact_blocks if b.label == "On-chain totalSupply() (Ethereum)")
    effective = next(b for b in fact_blocks if b.label == "Effective supply (post Burn Cycle 1)")
    assert "1,500,000,000" in onchain.value
    assert "1,018,545,702" in effective.value
    assert onchain.as_of and effective.as_of


async def test_supply_question_prefers_live_kpi_over_facts(stub_stores):
    stub_stores.kpi.redis.seed_kpi(
        "onchain_eth", "total_supply", {"raw": 1500000000000000000000000000, "cpx": 1500000000}
    )
    stub_stores.kpi.redis.seed_kpi(
        "onchain", "effective_supply_cpx", {"raw": 1018545702000000000000000000, "cpx": 1018545702}
    )

    response = await answer_question("total supply?", stub_stores)
    assert "kpi:onchain_eth:total_supply" in response.meta.kpis_used
    assert "kpi:onchain:effective_supply_cpx" in response.meta.kpis_used


async def test_supply_question_falls_back_to_facts_when_kpi_stale(stub_stores):
    stub_stores.kpi.redis.seed_kpi(
        "onchain_eth", "total_supply", {"cpx": 1500000000}, fetched_at="2020-01-01T00:00:00Z", stale_after_s=1800
    )
    response = await answer_question("total supply?", stub_stores)
    assert "tokenomics.onchain_total_supply_eth" in response.meta.facts_used
    assert "kpi:onchain_eth:total_supply" not in response.meta.kpis_used


# ──────────────────────────── facts-only Q&A ────────────────────────────


async def test_facts_only_question_answers_kind_faq(stub_stores):
    response = await answer_question("where can I claim my tokens?", stub_stores)
    assert response.meta.answer_kind in ("faq", "refusal")
    if response.meta.answer_kind == "faq":
        assert response.meta.facts_used


async def test_fact_citation_with_internal_source_url_is_never_linked(stub_stores, monkeypatch):
    # Production audit, 2026-08-18: several facts.yaml entries carry an
    # `internal://...` source_url (provenance notes, never meant to be
    # user-facing) -- qa/router.py must never turn that into a citation
    # link, even though the fact's VALUE still informs the LLM's context
    # (see Config.ALLOWED_LINK_PREFIXES).
    from century_core.qa import facts_search as facts_search_module
    from century_core.tests.conftest import make_fact

    internal_fact = make_fact(
        "Some internal-only provenance value",
        source_url="internal://content-audit-2026-07-20",
    )

    def fake_search_facts(store, question, limit=3):
        return [("test.internal_source_fact", internal_fact)]

    monkeypatch.setattr(facts_search_module, "search_facts", fake_search_facts)

    response = await answer_question("tell me something", stub_stores)

    assert "test.internal_source_fact" in response.meta.facts_used
    link_urls = [item.url for b in response.blocks if b.type == "links" for item in b.items]
    assert not any(url.startswith("internal://") for url in link_urls)


async def test_unanswerable_question_refuses_with_official_link(stub_stores):
    response = await answer_question("xyzzy plugh unrelated nonsense query", stub_stores)
    assert response.meta.answer_kind == "refusal"
    links = [b for b in response.blocks if b.type == "links"]
    assert links and any("ciphex.io" in item.url for item in links[0].items)


# ─────────────────────────────── RAG path ───────────────────────────────


@dataclass
class _FakeChunk:
    content: str
    title: str
    date: str
    source_url: str
    slug: str
    kind: str
    score: float


async def test_rag_hit_produces_rag_answer_kind(stub_stores, monkeypatch):
    # source_url/slug use the "ecosystem-update-*" naming convention -- the
    # only approved RAG source per the Bot Parameter Requirements
    # (2026-08-18; corpus = Internal Updates only, see qa/router.py's
    # _is_excluded_rag_source). A legacy publications-style slug like
    # "algorithmic-austerity" would be dropped from citations.
    async def fake_retrieve(conn, provider, query, top_k=4):
        return [
            _FakeChunk(
                content="Tiered activation reduces CPX emissions via self-optimizing contract logic.",
                title="Self-Optimizing Smart Contracts",
                date="January 28, 2025",
                source_url="https://ciphex.io/assets/documents/ecosystem-update-jan28-25.pdf",
                slug="ecosystem-update-jan28-25",
                kind="pdf",
                score=0.9,
            )
        ]

    monkeypatch.setattr("pubs_rag.retrieval.retrieve", fake_retrieve)
    stub_stores.rag_conn = object()  # any non-None sentinel
    stub_stores.rag_provider = object()

    # Deliberately avoids "supply"/"burn" wording -- those now route to the
    # deterministic supply path (is_supply_question) before RAG is ever
    # consulted; see test_qa_router's supply-distinction tests and
    # test_qa_supply_burn_phrasing_routes_to_deterministic_supply_path below.
    response = await answer_question("tell me about the self-optimizing smart contracts paper", stub_stores)
    assert response.meta.answer_kind == "rag"
    links = [b for b in response.blocks if b.type == "links"][0]
    assert any("ecosystem-update-jan28-25" in item.url for item in links.items)


async def test_rag_hits_from_same_document_are_deduped_in_citations(stub_stores, monkeypatch):
    async def fake_retrieve(conn, provider, query, top_k=4):
        return [
            _FakeChunk(
                content=f"chunk {i} about self-optimizing contract logic",
                title="Self-Optimizing Smart Contracts",
                date="January 28, 2025",
                source_url="https://ciphex.io/assets/documents/ecosystem-update-jan28-25.pdf",
                slug="ecosystem-update-jan28-25",
                kind="pdf",
                score=0.9 - i * 0.01,
            )
            for i in range(3)
        ]

    monkeypatch.setattr("pubs_rag.retrieval.retrieve", fake_retrieve)
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = object()

    # Avoids "burn"/"supply" wording -- see test_rag_hit_produces_rag_answer_kind.
    response = await answer_question("self-optimizing smart contract mechanics", stub_stores)
    links = [b for b in response.blocks if b.type == "links"][0]
    matching = [item for item in links.items if "ecosystem-update-jan28-25" in item.url]
    assert len(matching) == 1  # not 3 identical citations for one document


async def test_rag_hit_from_excluded_publications_page_is_never_cited(stub_stores, monkeypatch):
    # Corpus policy backstop (Bot Parameter Requirements, 2026-08-18): even
    # if a stale RAG hit somehow still carries an Insights & Publications
    # source (e.g. a document ingested before the policy landed, still
    # sitting in Postgres), it must never appear as a citation link -- see
    # qa/router.py's _is_excluded_rag_source.
    async def fake_retrieve(conn, provider, query, top_k=4):
        return [
            _FakeChunk(
                content="Burn cycle mechanics from a legacy publications-era document.",
                title="Algorithmic Austerity",
                date="January 28, 2025",
                source_url="https://ciphex.io/assets/documents/algorithmic-austerity.pdf",
                slug="algorithmic-austerity",
                kind="pdf",
                score=0.9,
            )
        ]

    monkeypatch.setattr("pubs_rag.retrieval.retrieve", fake_retrieve)
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = object()

    response = await answer_question("tell me about the algorithmic austerity paper", stub_stores)
    link_urls = [item.url for b in response.blocks if b.type == "links" for item in b.items]
    assert not any("algorithmic-austerity" in url for url in link_urls)


async def test_rag_hit_from_excluded_publications_page_url_is_never_cited(stub_stores, monkeypatch):
    # Same policy, exercised via the page URL shape rather than the PDF
    # asset shape.
    async def fake_retrieve(conn, provider, query, top_k=4):
        return [
            _FakeChunk(
                content="A chunk whose source is the excluded page itself.",
                title="Insights & Publications",
                date="January 1, 2026",
                source_url="https://ciphex.io/insights-and-publications",
                slug="insights-and-publications",
                kind="pdf",
                score=0.9,
            )
        ]

    monkeypatch.setattr("pubs_rag.retrieval.retrieve", fake_retrieve)
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = object()

    response = await answer_question("tell me about the ciphex publications page", stub_stores)
    link_urls = [item.url for b in response.blocks if b.type == "links" for item in b.items]
    assert not any("insights-and-publications" in url for url in link_urls)


async def test_rag_hits_below_min_score_are_dropped(stub_stores, monkeypatch):
    async def fake_retrieve(conn, provider, query, top_k=4):
        return [
            _FakeChunk(
                content="irrelevant low-score chunk",
                title="X",
                date=None,
                source_url="https://ciphex.io/x.pdf",
                slug="x",
                kind="pdf",
                score=0.0,
            )
        ]

    monkeypatch.setattr("pubs_rag.retrieval.retrieve", fake_retrieve)
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = object()

    response = await answer_question("xyzzy plugh unrelated nonsense query", stub_stores)
    assert response.meta.answer_kind == "refusal"


async def test_rag_min_score_raised_drops_smalltalk_matched_chunks(stub_stores, monkeypatch):
    # Go-live incident 2026-08-17: with the old default (0.05), a chunk
    # scoring well above that but still not genuinely relevant (e.g. a
    # partial vocabulary overlap on a smalltalk-ish query) was cited. 0.2
    # cleared the old threshold but must be dropped by the new one (0.3) --
    # see Config.RAG_MIN_SCORE.
    from century_core.config import Config

    async def fake_retrieve(conn, provider, query, top_k=4):
        return [
            _FakeChunk(
                content="tangentially related chunk",
                title="Growth & Expansion RFP Deadline",
                date="2025",
                source_url="https://ciphex.io/assets/documents/rfp.pdf",
                slug="rfp",
                kind="pdf",
                score=0.2,
            )
        ]

    monkeypatch.setattr("pubs_rag.retrieval.retrieve", fake_retrieve)
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = object()

    assert Config.RAG_MIN_SCORE >= 0.3
    # Same nonsense query as test_rag_hits_below_min_score_are_dropped (no
    # fact hits either) so the only thing standing between this and a
    # refusal is the RAG score filter -- a score of 0.2 cleared the old
    # 0.05 default but must not clear the raised 0.3 threshold.
    response = await answer_question("xyzzy plugh unrelated nonsense query", stub_stores)
    assert response.meta.answer_kind == "refusal"


# ────────────────────────── guardrail enforcement ──────────────────────────


async def test_llm_solicitation_output_is_caught_and_falls_back_to_refusal(stub_stores):
    stub_stores.llm._response = "You should buy CPX now, it's a great time to invest!"
    response = await answer_question("where can I claim my tokens?", stub_stores)
    assert response.meta.answer_kind == "refusal"


async def test_llm_banned_price_output_is_caught(stub_stores):
    stub_stores.llm._response = "The new round is priced at $0.25 per CPX."
    response = await answer_question("where can I claim my tokens?", stub_stores)
    assert response.meta.answer_kind == "refusal"


async def test_llm_unsourced_number_is_caught(stub_stores):
    # 424242 does not appear anywhere in facts.yaml context for this query.
    stub_stores.llm._response = "The claim portal has processed 424242 claims."
    response = await answer_question("where can I claim my tokens?", stub_stores)
    assert response.meta.answer_kind == "refusal"


async def test_llm_grounded_answer_passes_through(stub_stores):
    stub_stores.llm._response = "You can claim your tokens at the official claim portal."
    response = await answer_question("where can I claim my tokens?", stub_stores)
    assert response.meta.answer_kind == "faq"
    paragraphs = [b for b in response.blocks if b.type == "paragraph"]
    assert paragraphs and paragraphs[0].md == "You can claim your tokens at the official claim portal."


# ─────────────────────── unknown/refusal-style LLM output ───────────────────────
# Go-live incident 2026-08-17: "write me a poem" got a correct "I don't
# know" answer padded with three irrelevant publication citations. See
# guardrails.is_unknown_answer and its use in qa/router.answer_question.


async def test_stub_llm_unknown_answer_strips_all_citations(stub_stores):
    stub_stores.llm._response = "I don't know how to create a poem. For more information, please visit the official Ciphex site."
    # "where can I claim my tokens?" normally produces real fact hits (see
    # test_llm_grounded_answer_passes_through above) -- this proves the
    # unknown-answer detector strips citations even when hits existed, not
    # just when they didn't.
    response = await answer_question("where can I claim my tokens?", stub_stores)
    assert response.meta.answer_kind == "refusal"
    assert response.meta.facts_used == []
    links_blocks = [b for b in response.blocks if b.type == "links"]
    assert len(links_blocks) == 1
    assert len(links_blocks[0].items) == 1
    assert links_blocks[0].items[0].url == "https://ciphex.io"
    paragraphs = [b for b in response.blocks if b.type == "paragraph"]
    assert paragraphs and paragraphs[0].md == stub_stores.llm._response


async def test_stub_llm_refusal_variants_are_all_detected(stub_stores):
    for phrasing in [
        "I don't know the actual token holder number for CPX yet.",
        "I cannot answer that question with certainty.",
        "I'm not able to help with that request.",
        "Sorry, I don't have that information.",
    ]:
        stub_stores.llm._response = phrasing
        response = await answer_question("where can I claim my tokens?", stub_stores)
        assert response.meta.answer_kind == "refusal", phrasing


async def test_llm_answer_that_merely_mentions_dont_know_mid_sentence_is_not_swallowed(stub_stores):
    # The detector is anchored at the START of the answer -- a real grounded
    # answer that happens to mention uncertainty later must not be treated
    # as a refusal.
    stub_stores.llm._response = "You can claim your tokens at the official portal, though I don't know the exact processing time."
    response = await answer_question("where can I claim my tokens?", stub_stores)
    assert response.meta.answer_kind == "faq"


# ───────────────────────── off-topic/smalltalk short-circuit ─────────────────────────
# Go-live incident 2026-08-17 regression: "write me a poem" must never reach
# facts search or the LLM at all. See qa/offtopic.py.


def test_is_offtopic_question_triggers_on_greetings_and_smalltalk():
    assert is_offtopic_question("hi")
    assert is_offtopic_question("hey there")
    assert is_offtopic_question("hello!")
    assert is_offtopic_question("thanks")
    assert is_offtopic_question("thank you")
    assert is_offtopic_question("write me a poem")
    assert is_offtopic_question("write me a song")
    assert is_offtopic_question("tell me a joke")
    assert is_offtopic_question("who are you")
    assert is_offtopic_question("who are you?")


def test_is_offtopic_question_conservative_does_not_swallow_real_questions():
    assert not is_offtopic_question("which chain is cpx on")
    assert not is_offtopic_question("history of ciphex")
    assert not is_offtopic_question("what is the total supply of CPX?")
    assert not is_offtopic_question("where can I claim my tokens?")
    assert not is_offtopic_question("what other information about ciphex can you tell me?")


async def test_offtopic_write_me_a_poem_gets_scope_reply_with_no_citations(stub_stores):
    # Exact transcript regression case.
    response = await answer_question("write me a poem", stub_stores)
    assert response.meta.answer_kind == "refusal"
    assert response.meta.facts_used == []
    links_blocks = [b for b in response.blocks if b.type == "links"]
    assert len(links_blocks) == 1
    assert len(links_blocks[0].items) == 1
    assert links_blocks[0].items[0].url == "https://ciphex.io"
    paragraphs = [b for b in response.blocks if b.type == "paragraph"]
    assert paragraphs and "Century" in paragraphs[0].md
    assert "/help" in paragraphs[0].md


async def test_offtopic_greeting_short_circuits_before_facts_search(stub_stores):
    response = await answer_question("hey there!", stub_stores)
    assert response.meta.answer_kind == "refusal"
    assert response.meta.facts_used == []


# ───────────────────────── holder-count deterministic route ─────────────────────────
# Go-live incident 2026-08-17 regression: "what is the actual token holder
# number for ciphex?" dead-ended with irrelevant citations, including a
# link labeled with the raw fact key. See qa/holders.py.


def test_is_holder_question_triggers_on_holder_keyword():
    assert is_holder_question("what is the actual token holder number for ciphex?")
    assert is_holder_question("how many holders does CPX have")
    assert is_holder_question("token holder count")
    assert is_holder_question("number of holders")


def test_is_holder_question_conservative_does_not_swallow_supply_questions():
    assert not is_holder_question("how many tokens are there")
    assert not is_holder_question("what is the total supply of CPX?")
    assert not is_holder_question("how many tokens were burned")


async def test_holder_question_gets_deterministic_etherscan_answer(stub_stores):
    # Exact transcript regression case.
    response = await answer_question("what is the actual token holder number for ciphex?", stub_stores)
    assert response.meta.answer_kind == "faq"
    paragraphs = [b for b in response.blocks if b.type == "paragraph"]
    assert paragraphs and "Etherscan" in paragraphs[0].md
    links_blocks = [b for b in response.blocks if b.type == "links"]
    assert len(links_blocks) == 1
    assert len(links_blocks[0].items) == 1
    item = links_blocks[0].items[0]
    assert "etherscan.io" in item.url
    assert "18b33687d1c804" in item.url
    # The raw fact key must never leak as the link label (defect 3).
    assert "." not in item.label
    assert item.label != "contracts.cpx_token_ethereum"


async def test_holder_question_checked_before_price_and_offtopic(stub_stores):
    # "holder" doesn't overlap with price/offtopic vocabulary, but this
    # locks in that the holder route wins over the generic facts+LLM path.
    response = await answer_question("how many holders does CPX have?", stub_stores)
    assert response.meta.answer_kind == "faq"
    links_blocks = [b for b in response.blocks if b.type == "links"]
    assert any("etherscan.io" in item.url for item in links_blocks[0].items)


# ───────────────────────── human-readable fact-key labels ─────────────────────────
# Defect 3 regression: a raw dotted fact key must never appear as a
# user-visible link label. See qa/labels.py.


def test_humanize_fact_key_never_returns_raw_dotted_key():
    for key in [
        "tokenomics.onchain_total_supply_eth",
        "tokenomics.max_supply_cpx",
        "contracts.cpx_token_ethereum",
        "identity.legal_entity",
        "round-terms.legacy_2025_status",
    ]:
        label = humanize_fact_key(key)
        assert "." not in label
        assert label != key


def test_humanize_fact_key_exact_transcript_key():
    assert humanize_fact_key("tokenomics.onchain_total_supply_eth") == "CPX Total Supply (Ethereum)"


async def test_facts_only_question_never_leaks_raw_key_as_link_label(stub_stores):
    response = await answer_question("where can I claim my tokens?", stub_stores)
    links_blocks = [b for b in response.blocks if b.type == "links"]
    for block in links_blocks:
        for item in block.items:
            assert "." not in item.label, f"raw-looking fact key leaked as label: {item.label!r}"


# --- Listing-intent routing (live test regression, 2026-08-18) -------------

LISTING_QUESTIONS = [
    "when does ciphex start trading on exchanges",
    "is CPX listed on an exchange?",
    "when is the DEX listing",
    "what CEX will carry CPX",
    "where can I buy CPX on an exchange",
]

NOT_LISTING_QUESTIONS = [
    # Contribution Program vocabulary: "exchange value" without timing intent
    "what is the exchange value of each token",
    # supply question must keep winning its earlier route
    "what is the total supply of CPX",
]


@pytest.mark.parametrize("question", LISTING_QUESTIONS)
async def test_listing_intent_routes_to_deterministic_price_answer(question, stub_stores):
    response = await answer_question(question, stub_stores)
    text = " ".join(getattr(b, "md", getattr(b, "text", "")) for b in response.blocks)
    assert "not yet listed" in text
    assert response.meta.answer_kind == "command"


@pytest.mark.parametrize("question", NOT_LISTING_QUESTIONS)
async def test_non_listing_questions_are_not_swallowed(question, stub_stores):
    from century_core.qa.price import is_listing_question
    assert not is_listing_question(question)
