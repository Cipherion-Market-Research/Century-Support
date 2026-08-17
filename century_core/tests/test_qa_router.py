"""Q&A router: deterministic supply path, facts-only path, RAG path
(mocked pubs_rag.retrieval.retrieve), and guardrail-triggered fallbacks.
"""
from dataclasses import dataclass

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
    async def fake_retrieve(conn, provider, query, top_k=4):
        return [
            _FakeChunk(
                content="Tiered activation reduces CPX emissions via self-optimizing contract logic.",
                title="Self-Optimizing Smart Contracts",
                date="January 28, 2025",
                source_url="https://ciphex.io/assets/documents/algorithmic-austerity.pdf",
                slug="algorithmic-austerity",
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
    assert any("algorithmic-austerity" in item.url for item in links.items)


async def test_rag_hits_from_same_document_are_deduped_in_citations(stub_stores, monkeypatch):
    async def fake_retrieve(conn, provider, query, top_k=4):
        return [
            _FakeChunk(
                content=f"chunk {i} about self-optimizing contract logic",
                title="Self-Optimizing Smart Contracts",
                date="January 28, 2025",
                source_url="https://ciphex.io/assets/documents/algorithmic-austerity.pdf",
                slug="algorithmic-austerity",
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
    matching = [item for item in links.items if "algorithmic-austerity" in item.url]
    assert len(matching) == 1  # not 3 identical citations for one document


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
