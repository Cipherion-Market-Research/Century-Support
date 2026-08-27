"""Q&A router: deterministic supply path, facts-only path, RAG path
(mocked pubs_rag.retrieval.retrieve), and guardrail-triggered fallbacks.
"""
import pytest
from dataclasses import dataclass

from century_core.qa.contribution import is_contribution_question
from century_core.qa.holders import is_holder_question
from century_core.qa.intro import is_intro_question
from century_core.qa.labels import humanize_fact_key
from century_core.qa.language import is_non_english_question
from century_core.qa.offtopic import is_offtopic_question
from century_core.qa.price import is_buy_question, is_listing_question, is_price_question
from century_core.qa.router import answer_question, build_context
from century_core.tests.conftest import make_fact
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


# ─────────────── supply: mint/creation synonyms (live tester feedback, 2026-08-26) ───────────────
# "will there be additional CPX tokens created?" missed the supply route
# entirely. See qa/supply.py's _SUPPLY_TRIGGERS.


def test_is_supply_question_triggers_on_mint_creation_synonyms():
    assert is_supply_question("will there be additional CPX tokens created?")
    assert is_supply_question("can more CPX be minted?")
    assert is_supply_question("is CPX still being minted")
    assert is_supply_question("what is the minting schedule")


async def test_mint_creation_question_routes_to_deterministic_supply_path(stub_stores):
    # Exact transcript regression case.
    response = await answer_question("will there be additional CPX tokens created?", stub_stores)
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    labels = {b.label for b in fact_blocks}
    assert "On-chain totalSupply() (Ethereum)" in labels
    assert "Effective supply (post Burn Cycle 1)" in labels


# ─────────── supply: qualitative "type/model/kind" framing (live tester feedback, 2026-08-26) ───────────
# "what type of supply model does CPX use?" previously answered with
# numbers only, never naming the model. See qa/supply.py's
# _is_qualitative_supply_question.


async def test_qualitative_supply_question_prepends_model_sentence(stub_stores):
    response = await answer_question("what type of supply model does CPX use?", stub_stores)
    paragraphs = [b for b in response.blocks if b.type == "paragraph"]
    assert any(
        "fixed-maximum, deflationary supply model with scheduled burn cycles" in p.md for p in paragraphs
    )
    # The numbers still follow -- this is additive, not a replacement.
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    labels = {b.label for b in fact_blocks}
    assert "On-chain totalSupply() (Ethereum)" in labels


async def test_plain_supply_question_has_no_qualitative_sentence(stub_stores):
    response = await answer_question("what is the total supply of CPX?", stub_stores)
    paragraphs = [b for b in response.blocks if b.type == "paragraph"]
    assert not any("fixed-maximum, deflationary supply model" in p.md for p in paragraphs)


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


# ───────── price: "value"/"valuation" triggers (live tester feedback, 2026-08-26) ─────────
# "what is the value of CPX?" fell through to RAG/LLM x2. See qa/price.py's
# _PRICE_TRIGGERS.


def test_is_price_question_triggers_on_value_valuation():
    assert is_price_question("what is the value of CPX?")
    assert is_price_question("what is the valuation of CPX?")


async def test_value_question_routes_to_deterministic_price_command(stub_stores):
    # Exact transcript regression case.
    response = await answer_question("what is the value of CPX?", stub_stores)
    assert response.meta.answer_kind == "command"
    heading = next(b for b in response.blocks if b.type == "heading")
    assert heading.text == "CPX Price"


def test_is_listing_question_still_conservative_against_contribution_vocabulary_with_value_trigger():
    # "value" is now a price trigger, but is_listing_question's own
    # exchange+timing pairing is unaffected by that -- the Contribution
    # Program's "exchange value of each token" phrasing has no timing token
    # at all (not even the newly-added "available"), so it still doesn't
    # route via is_listing_question.
    assert not is_listing_question("what is the exchange value of each token")


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

    def fake_search_facts_scored(store, question, limit=3):
        return [(1.0, "test.internal_source_fact", internal_fact)]

    monkeypatch.setattr(facts_search_module, "search_facts_scored", fake_search_facts_scored)

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


# --- DEX/CEX hijack fix (live tester feedback, 2026-08-26) -----------------
# "can I do autonomous portfolio management on the DEX?" / "...on the CEX?"
# routed to the price/listing answer purely off the bare "dex"/"cex" token
# -- flat wrong x2, no listing/timing intent at all. See qa/price.py:
# is_listing_question now requires a timing/trading token alongside a bare
# "dex"/"cex" ("listed"/"listing" stay sufficient alone).

CAPABILITY_QUESTIONS_MENTIONING_DEX_CEX = [
    "can I do autonomous portfolio management on the DEX?",
    "can I do autonomous portfolio management on the CEX?",
]


@pytest.mark.parametrize("question", CAPABILITY_QUESTIONS_MENTIONING_DEX_CEX)
def test_bare_dex_cex_no_longer_sufficient_for_listing_question(question):
    assert not is_listing_question(question)


@pytest.mark.parametrize("question", CAPABILITY_QUESTIONS_MENTIONING_DEX_CEX)
async def test_capability_questions_mentioning_dex_cex_no_longer_route_to_price(question, stub_stores):
    response = await answer_question(question, stub_stores)
    assert response.meta.answer_kind != "command"


def test_listing_verb_alone_still_sufficient_for_dex_cex():
    # "listed"/"listing" remain standalone-sufficient triggers even when
    # paired with dex/cex -- this is an existing LISTING_QUESTIONS case
    # ("when is the DEX listing") re-asserted directly against the
    # tightened detector.
    assert is_listing_question("when is the DEX listing")


def test_dex_cex_with_timing_token_still_routes():
    assert is_listing_question("will CPX be listed on a DEX soon")
    assert is_listing_question("when will CPX trade on a CEX")


# --- "available"/"availability" timing-token coverage (live tester feedback, 2026-08-26) ---
# "where will CPX be available?" (also see guardrails.py's forward-listing-
# promise ban for the same tester quote). Deliberately conservative: added
# as a *timing* token (paired with "exchange(s)"), not a standalone listing
# token -- see qa/price.py's _TIMING_TOKENS comment for why.


def test_available_timing_token_pairs_with_exchange():
    assert is_listing_question("will CPX be available on an exchange?")
    assert is_listing_question("is CPX available on any exchange yet?")


def test_available_requires_a_brand_token_to_route():
    # "available" paired with a CPX/token word IS listing intent (the P0
    # tester question "where will CPX be available?" must route to the
    # deterministic answer -- acceptance-battery ruling, 2026-08-26), but
    # bare availability of anything else stays conservative.
    assert is_listing_question("where will CPX be available?")
    assert not is_listing_question("where is the demo available?")
    assert not is_listing_question("is the claim portal available?")


# ───────────────────────── non-English input gate (live tester feedback, 2026-08-19) ─────────────────────────
# A Mandarin message got a confused English reply -- see qa/language.py.
# Checked FIRST in the router, before offtopic.

NON_ENGLISH_QUESTIONS = [
    "你好,我想问一下CPX代币是什么",  # Mandarin
    "Привет, объясните мне про CPX",  # Cyrillic
    "مرحبا، ما هو رمز CPX؟",  # Arabic
]

ENGLISH_PASSTHROUGH_QUESTIONS = [
    "How do I claim my tokens? 🎉",  # English + one emoji
    "What is the contract address 0x18b33687d1c804Dd4ea6c82106e54923c23a652E?",  # hex digits
    "¿cómo?",  # Latin-script non-English -- known limitation, explicitly out of scope
]


@pytest.mark.parametrize("question", NON_ENGLISH_QUESTIONS)
def test_is_non_english_question_triggers_on_non_latin_script(question):
    assert is_non_english_question(question)


@pytest.mark.parametrize("question", ENGLISH_PASSTHROUGH_QUESTIONS)
def test_is_non_english_question_does_not_trigger_on_latin_script(question):
    assert not is_non_english_question(question)


@pytest.mark.parametrize("question", NON_ENGLISH_QUESTIONS)
async def test_non_english_question_gets_deterministic_english_only_reply(question, stub_stores):
    response = await answer_question(question, stub_stores)
    assert response.meta.answer_kind == "refusal"
    assert response.meta.facts_used == []
    paragraphs = [b for b in response.blocks if b.type == "paragraph"]
    assert paragraphs and "English only" in paragraphs[0].md
    links_blocks = [b for b in response.blocks if b.type == "links"]
    assert len(links_blocks) == 1
    assert links_blocks[0].items[0].url == "https://ciphex.io"


async def test_non_english_gate_checked_before_offtopic_and_facts(stub_stores):
    # A non-English message must never reach facts search or the LLM, and
    # must win over anything else (there's no meaningful offtopic/greeting
    # classification of non-Latin-script text).
    response = await answer_question("你好,我想问一下CPX代币是什么", stub_stores)
    assert response.meta.answer_kind == "refusal"


# ───────────────────────── buy-intent routing (live tester feedback, 2026-08-19) ─────────────────────────
# "How do I buy CPX" fell through to RAG and served a 2025-era update's
# stale claim ("initial DEX listing is targeted for September 2025") -- the
# worst answer surfaced in that test pass. See qa/price.py's
# is_buy_question.

BUY_QUESTIONS = [
    "How do I buy CPX",
    "how can I purchase CPX tokens",
    "I want to invest in ciphex",
    "where do I acquire the CPX coin",
]

NOT_BUY_QUESTIONS = [
    # buy-verb token present, but no CPX/token word -- must not be swallowed
    "when will contributors buy in",
    # CPX/token word present, but no buy-verb -- supply/holder/stats questions unaffected
    "how many tokens are there",
    "what is the total supply of CPX?",
    "how many holders does CPX have",
    "how many tokens were burned",
]


@pytest.mark.parametrize("question", BUY_QUESTIONS)
def test_is_buy_question_triggers_on_buy_verb_and_token_word(question):
    assert is_buy_question(question)


@pytest.mark.parametrize("question", NOT_BUY_QUESTIONS)
def test_is_buy_question_conservative_does_not_swallow_unrelated_questions(question):
    assert not is_buy_question(question)


async def test_buy_question_routes_to_deterministic_price_answer(stub_stores):
    # Exact transcript regression case.
    response = await answer_question("How do I buy CPX", stub_stores)
    assert response.meta.answer_kind == "command"
    heading = next(b for b in response.blocks if b.type == "heading")
    assert heading.text == "CPX Price"
    text = " ".join(getattr(b, "md", getattr(b, "text", "")) for b in response.blocks)
    assert "not yet listed" in text


async def test_supply_holder_stats_questions_unaffected_by_buy_intent_route(stub_stores):
    response = await answer_question("what is the total supply of CPX?", stub_stores)
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    labels = {b.label for b in fact_blocks}
    assert "On-chain totalSupply() (Ethereum)" in labels

    response = await answer_question("how many holders does CPX have", stub_stores)
    assert response.meta.answer_kind == "faq"
    links_blocks = [b for b in response.blocks if b.type == "links"]
    assert any("etherscan.io" in item.url for item in links_blocks[0].items)


# ───────────────────────── intro-intent routing (live tester feedback, 2026-08-19) ─────────────────────────
# "what is cipex", "what is CPHEX", "Tell me a little bit about what CipheX
# is", "I want to understand Ciphex and the CPX token" all went to RAG and
# produced unapproved paraphrases citing old PDFs. See qa/intro.py; routes
# to century_core.commands.ecosystem.handle_ecosystem.

INTRO_QUESTIONS = [
    "what is cipex",
    "what is CPHEX",
    "Tell me a little bit about what CipheX is",
    "I want to understand Ciphex and the CPX token",
]

NOT_INTRO_QUESTIONS = [
    "what is the total supply",
    "what is the contract address",
    "what is the exchange value",
]


@pytest.mark.parametrize("question", INTRO_QUESTIONS)
def test_is_intro_question_triggers_on_transcript_phrasings(question):
    assert is_intro_question(question)


@pytest.mark.parametrize("question", NOT_INTRO_QUESTIONS)
def test_is_intro_question_conservative_does_not_swallow_unrelated_questions(question):
    assert not is_intro_question(question)


@pytest.mark.parametrize("question", INTRO_QUESTIONS)
async def test_intro_question_routes_to_deterministic_ecosystem_overview(question, stub_stores):
    response = await answer_question(question, stub_stores)
    assert response.meta.answer_kind == "command"
    heading = next(b for b in response.blocks if b.type == "heading")
    assert heading.text == "The Ciphex Ecosystem"


async def test_total_supply_question_still_wins_over_intro_route(stub_stores):
    # "what is the total supply" must stay on the supply route, checked
    # before intro in the router.
    response = await answer_question("what is the total supply of CPX", stub_stores)
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    labels = {b.label for b in fact_blocks}
    assert "On-chain totalSupply() (Ethereum)" in labels


# ───────────── intro over-capture fix (live tester feedback, 2026-08-26) ─────────────
# "what is Ciphex Alpha?" (should hit products.ciphex_alpha_description via
# facts search), "what is ciphex's relationship with CertiK/Kevin O'Brien/
# Steve Martin" (possessive), and "tell me about ciphex connect" all got the
# canned ecosystem block instead of their more specific answer. See
# qa/intro.py's _TERMINAL_SUFFIX.

OVER_CAPTURE_QUESTIONS = [
    "what is Ciphex Alpha?",
    "what is ciphex's relationship with CertiK/Kevin O'Brien/Steve Martin",
    "tell me about ciphex connect",
]


@pytest.mark.parametrize("question", OVER_CAPTURE_QUESTIONS)
def test_is_intro_question_no_longer_over_captures_transcript_phrasings(question):
    assert not is_intro_question(question)


async def test_ciphex_alpha_question_answers_from_facts_not_intro(stub_stores):
    # Scope: is_intro_question must not swallow this question (see
    # test_is_intro_question_no_longer_over_captures_transcript_phrasings
    # above) -- it must fall through to the ordinary facts-search/RAG path
    # rather than the canned ecosystem block. Ranking of facts_search's
    # top-3 for this exact phrasing is a separate, pre-existing concern
    # (naive keyword-overlap scoring, unrelated to intro-detection) --
    # covered separately below via facts_search directly.
    response = await answer_question("what is Ciphex Alpha?", stub_stores)
    assert response.meta.answer_kind != "command"


def test_ciphex_alpha_description_is_discoverable_via_facts_search(stub_stores):
    from century_core.qa import facts_search

    hits = facts_search.search_facts(stub_stores.facts, "what is Ciphex Alpha?", limit=10)
    assert any(key == "products.ciphex_alpha_description" for key, _ in hits)


@pytest.mark.parametrize("question", INTRO_QUESTIONS)
def test_intro_regressions_still_trigger_after_terminal_word_tightening(question):
    # Existing passing regressions ("what is cipex", "tell me a little bit
    # about what CipheX is", "I want to understand Ciphex and the CPX
    # token", "what is CPHEX") must all still match after tightening the
    # "what is <brand>" / "tell me about <brand>" patterns to require the
    # brand be the terminal content word.
    assert is_intro_question(question)


# ───────────────────── era-framing for legacy facts (item 3, live tester feedback, 2026-08-26) ─────────────────────
# "how many months will contributions be permitted?" -> "12 months" -- the
# LLM presented round-terms.legacy_2025_vesting_months (the concluded 2025
# round) as if it described the current Contribution Program. See
# qa/router.py's build_context / _fact_context_line.


def test_build_context_prefixes_legacy_2025_facts_with_era_marker():
    legacy_fact = make_fact(12, source_url="https://ciphex.io/assets/documents/ecosystem-update-jul22-25.pdf")
    # Exact transcript regression question, paired directly with the legacy
    # fact it was mis-answered from.
    context, facts_used, _ = build_context(
        fact_hits=[("round-terms.legacy_2025_vesting_months", legacy_fact)],
        rag_hits=[],
    )
    assert "[LEGACY 2025 ROUND — CONCLUDED; not the current Contribution Program]" in context
    assert "round-terms.legacy_2025_vesting_months" in facts_used


def test_build_context_does_not_mark_non_legacy_facts():
    current_fact = make_fact(1500000000, source_url="https://ciphex.io/ciphex-token")
    context, _, _ = build_context(
        fact_hits=[("tokenomics.max_supply", current_fact)],
        rag_hits=[],
    )
    assert "LEGACY 2025 ROUND" not in context


# ───────────────────── link dedup across facts+RAG (item 8, live tester feedback, 2026-08-26) ─────────────────────
# rag_links and fact_links were each deduped internally but not against
# each other -- testers saw the same URL twice when a fact link and a RAG
# link happened to point at the same page. See qa/router.py's build_context.


def test_build_context_dedupes_links_across_facts_and_rag_by_url():
    shared_url = "https://ciphex.io/ciphex-token"
    fact = make_fact("ERC-20, deployed on Ethereum mainnet only", source_url=shared_url)
    rag_hit = _FakeChunk(
        content="CPX is an ERC-20 token.",
        title="CPX Token",
        date="August 26, 2026",
        source_url=shared_url,
        slug="ecosystem-update-aug26-26",
        kind="pdf",
        score=0.9,
    )
    _, _, link_items = build_context(
        fact_hits=[("tokenomics.token_standard", fact)],
        rag_hits=[rag_hit],
    )
    urls = [item.url for item in link_items]
    assert urls.count(shared_url) == 1


def test_build_context_keeps_distinct_urls_and_preserves_rag_first_order():
    fact = make_fact("value", source_url="https://ciphex.io/ciphex-token")
    rag_hit = _FakeChunk(
        content="content",
        title="RAG Title",
        date="August 26, 2026",
        source_url="https://ciphex.io/assets/documents/ecosystem-update-aug26-26.pdf",
        slug="ecosystem-update-aug26-26",
        kind="pdf",
        score=0.9,
    )
    _, _, link_items = build_context(
        fact_hits=[("tokenomics.token_standard", fact)],
        rag_hits=[rag_hit],
    )
    assert [item.url for item in link_items] == [rag_hit.source_url, fact.source_url]


# ───────────────────── contribution-intent deterministic route (item 1, Sprint 2, live tester feedback, 2026-08-26) ─────────────────────
# Five near-identical-intent questions got one good answer, three
# refusals, and one flat-wrong answer from facts_search + LLM ranking. See
# qa/contribution.py; routes to century_core.commands.contribute.handle_contribute.

CONTRIBUTION_QUESTIONS = [
    "when can I contribute?",
    "how long will the contribution program run?",
    "how many months will contributions be permitted?",
    "when does the contribution program start?",
    "how do I participate in the contribution program?",
    # "minimum" tuning (live tester feedback, 2026-08-26): answered well by
    # facts_search today, but routed here too since the deterministic
    # /contribute response states the exact tier minimums in the same
    # breath as the rest of the program terms.
    "what is the minimum contribution?",
]


@pytest.mark.parametrize("question", CONTRIBUTION_QUESTIONS)
def test_is_contribution_question_triggers_on_tester_phrasings(question):
    assert is_contribution_question(question)


@pytest.mark.parametrize("question", CONTRIBUTION_QUESTIONS)
async def test_contribution_question_routes_to_deterministic_contribute_command(question, stub_stores):
    response = await answer_question(question, stub_stores)
    assert response.meta.answer_kind == "command"
    heading = next(b for b in response.blocks if b.type == "heading")
    assert heading.text == "Ciphex Contribution Program (Phase I)"


async def test_minimum_contribution_question_response_contains_tier_minimums(stub_stores):
    # "what is the minimum contribution?" must state the actual tier
    # minimums (Early/Growth/Final), not just a generic status message.
    response = await answer_question("what is the minimum contribution?", stub_stores)
    text = " ".join(getattr(b, "md", getattr(b, "text", "")) for b in response.blocks)
    assert "1,000" in text
    assert "2,000" in text
    assert "3,000" in text


def test_is_contribution_question_conservative_does_not_swallow_buy_intent():
    assert not is_contribution_question("how do I buy CPX")


async def test_buy_intent_still_wins_over_contribution_route(stub_stores):
    # Buy-intent questions keep their existing deterministic /price route
    # -- checked before the contribution route in qa/router.py -- even
    # where a phrasing could plausibly overlap contribution vocabulary.
    response = await answer_question("how do I buy CPX", stub_stores)
    assert response.meta.answer_kind == "command"
    heading = next(b for b in response.blocks if b.type == "heading")
    assert heading.text == "CPX Price"


def test_is_contribution_question_conservative_does_not_swallow_unrelated_questions():
    assert not is_contribution_question("what is the total supply of CPX?")
    assert not is_contribution_question("where can I claim my tokens?")
    assert not is_contribution_question("what is the price of CPX?")


# ───────────────────── link relevance (item 3, Sprint 2, live tester feedback, 2026-08-26) ─────────────────────
# An irrelevant atlas-rwa-services link rode along on leadership questions,
# and an irrelevant financing-activities link rode along on a risk-
# management question -- both coincidental tie-matches that placed in the
# top-`limit` fact_hits despite scoring far below the fact that actually
# answers the question. See qa/router.py's linkable_fact_keys /
# _LINK_RELEVANCE_RATIO.


async def test_leadership_question_never_links_the_atlas_page(stub_stores):
    response = await answer_question("who is the CPX management team?", stub_stores)
    links_blocks = [b for b in response.blocks if b.type == "links"]
    for block in links_blocks:
        assert not any("atlas-rwa-services" in item.url for item in block.items)


async def test_risk_management_question_never_links_financing_activities(stub_stores):
    response = await answer_question("dynamic risk management", stub_stores)
    links_blocks = [b for b in response.blocks if b.type == "links"]
    for block in links_blocks:
        assert not any("financing-activities" in item.url for item in block.items)


def test_build_context_omits_link_for_fact_hit_outside_linkable_set():
    fact_a = make_fact("Value A", source_url="https://ciphex.io/a")
    fact_b = make_fact("Value B", source_url="https://ciphex.io/b")
    context, facts_used, link_items = build_context(
        fact_hits=[("test.a", fact_a), ("test.b", fact_b)],
        rag_hits=[],
        linkable_fact_keys={"test.a"},
    )
    # Both facts still enter context (grounding), regardless of link cap.
    assert facts_used == ["test.a", "test.b"]
    assert "[test.a]" in context
    assert "[test.b]" in context
    assert [item.url for item in link_items] == ["https://ciphex.io/a"]


def test_build_context_linkable_fact_keys_none_means_no_filtering():
    # Default (no threshold computed) preserves prior behavior: every
    # fact_hit is linkable.
    fact_a = make_fact("Value A", source_url="https://ciphex.io/a")
    context, _, link_items = build_context(fact_hits=[("test.a", fact_a)], rag_hits=[])
    assert [item.url for item in link_items] == ["https://ciphex.io/a"]


# ───────────────────── token-vs-system disambiguation (item 4, Sprint 2, live tester feedback, 2026-08-26) ─────────────────────
# "can the CPX token do autonomous trading?" (x2) got answers implying the
# CPX token itself trades. See qa/router.py's _TOKEN_VS_SYSTEM_NOTE.


def test_build_context_prepends_token_vs_system_note_when_alpha_fact_and_token_query_cooccur():
    alpha_fact = make_fact(
        "Ciphex Alpha is an autonomous market-intelligence and portfolio-management system.",
        source_url="https://ciphex.io/ciphex-alpha",
    )
    context, _, _ = build_context(
        fact_hits=[("products.ciphex_alpha_description", alpha_fact)],
        rag_hits=[],
        query="can the CPX token do autonomous trading?",
    )
    assert (
        "[NOTE: CPX is the ecosystem token; Ciphex Alpha is the autonomous system "
        "— do not attribute Alpha's capabilities to the token itself]" in context
    )


def test_build_context_omits_token_vs_system_note_without_token_word():
    alpha_fact = make_fact("Ciphex Alpha description.", source_url="https://ciphex.io/ciphex-alpha")
    context, _, _ = build_context(
        fact_hits=[("products.ciphex_alpha_description", alpha_fact)],
        rag_hits=[],
        query="what is Ciphex Alpha?",
    )
    assert "NOTE: CPX is the ecosystem token" not in context


def test_build_context_omits_token_vs_system_note_without_alpha_fact():
    other_fact = make_fact("Some other value.", source_url="https://ciphex.io/x")
    context, _, _ = build_context(
        fact_hits=[("some.other_key", other_fact)],
        rag_hits=[],
        query="what can the CPX token do?",
    )
    assert "NOTE: CPX is the ecosystem token" not in context


async def test_token_vs_system_question_built_context_contains_note(stub_stores):
    # Exact transcript regression: the built LLM context for this question
    # must contain the disambiguation note. StubLLMProvider echoes its
    # context back verbatim (see conftest/llm.py), so it's directly
    # observable on the response's first paragraph.
    response = await answer_question("can the CPX token do autonomous trading?", stub_stores)
    paragraphs = [b for b in response.blocks if b.type == "paragraph"]
    assert paragraphs
    assert "NOTE: CPX is the ecosystem token; Ciphex Alpha is the autonomous system" in paragraphs[0].md


# --- Acceptance-battery regressions (integration pass, 2026-08-26) ----------

@pytest.mark.parametrize("question", [
    "Will ciphex be able to provide autonomous portfolio management on DEX?",
    "Will CPX be able to provide autonomous portfolio management on DEX?",
])
async def test_dex_capability_questions_with_will_are_not_hijacked(question):
    from century_core.qa.price import is_listing_question
    assert not is_listing_question(question)


async def test_cpx_availability_question_routes_to_listing(stub_stores):
    response = await answer_question("where will CPX be available?", stub_stores)
    text = " ".join(getattr(b, "md", getattr(b, "text", "")) for b in response.blocks)
    assert response.meta.answer_kind == "command"
    assert "not yet listed" in text


def test_cex_carry_phrasing_still_routes():
    from century_core.qa.price import is_listing_question
    assert is_listing_question("what CEX will carry CPX")
    assert not is_listing_question("is a demo available")


@pytest.mark.parametrize("question", [
    "what is ciphex's relationship with Kevin O'Brien?",
    "what is CPX's relationship with Kevin O'Brien?",
    "what is Kevin O'Brien's role?",
])
async def test_relationship_questions_about_roster_names_answer_from_roster(question, stub_stores):
    response = await answer_question(question, stub_stores)
    text = " ".join(getattr(b, "md", getattr(b, "text", "")) for b in response.blocks)
    # the harvested page renders the typographic apostrophe (O’Brien);
    # assert on the apostrophe-free halves so the test is typography-proof
    assert "Kevin O" in text and "Brien" in text
    assert response.meta.answer_kind != "refusal"


async def test_relationship_question_about_non_roster_entity_passes_through(stub_stores):
    # CertiK is not a person on the leadership roster -- must keep flowing
    # to facts search (links.certik_skynet grounds it), never the roster.
    from century_core.qa.pages_roster import is_person_question
    assert not is_person_question("what is ciphex's relationship with CertiK?")
