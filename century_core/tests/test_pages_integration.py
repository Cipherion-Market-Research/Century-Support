"""Integration tests for the Sprint 3 pages-corpus hook in
century_core/qa/router.py -- page hits joining context/citations, page
links ranking between rag links and fact links, and the deterministic
team-roster short-circuit reached through answer_question() end to end.

Kept as a separate file from test_qa_router.py (rather than appended to
it) so this branch's footprint in that shared file stays at zero --
router.py's own edits are a small, clearly-delimited block (see its
"pages-corpus hook" comments) for the same reason.
"""
from dataclasses import dataclass

from century_core.qa.router import answer_question, build_context


@dataclass
class _FakePageChunk:
    content: str
    title: str
    slug: str
    score: float
    page_url: str


# ─────────────────────────── build_context ───────────────────────────


def test_build_context_backward_compatible_without_page_hits():
    # Pre-Sprint-3 callers (era-framing tests) call build_context(fact_hits,
    # rag_hits) with no third argument -- must keep working unchanged.
    context, facts_used, link_items = build_context([], [])
    assert context == ""
    assert facts_used == []
    assert link_items == []


def test_build_context_joins_page_hits_into_context_with_page_prefix():
    page_hit = _FakePageChunk(
        content="Ciphex Leadership Team brings decades of experience.",
        title="Ciphex Leadership Team",
        slug="leadership-team",
        score=0.5,
        page_url="https://ciphex.io/leadership-team",
    )
    context, facts_used, link_items = build_context([], [], [page_hit])
    assert "[page:leadership-team]" in context
    assert "Ciphex Leadership Team brings decades of experience." in context
    assert "https://ciphex.io/leadership-team" in context


def test_build_context_page_links_cite_the_page_url():
    page_hit = _FakePageChunk(
        content="chunk content",
        title="Ciphex Leadership Team",
        slug="leadership-team",
        score=0.5,
        page_url="https://ciphex.io/leadership-team",
    )
    _, _, link_items = build_context([], [], [page_hit])
    assert any(item.url == "https://ciphex.io/leadership-team" for item in link_items)
    assert any(item.label == "Ciphex Leadership Team" for item in link_items)


def test_build_context_dedupes_page_hits_from_same_page():
    hits = [
        _FakePageChunk(
            content=f"chunk {i}", title="T", slug="s", score=0.5, page_url="https://ciphex.io/s"
        )
        for i in range(3)
    ]
    _, _, link_items = build_context([], [], hits)
    page_links = [item for item in link_items if item.url == "https://ciphex.io/s"]
    assert len(page_links) == 1  # deduped, not 3 identical citations


def test_build_context_page_links_rank_between_rag_and_fact_links():
    from century_core.models import LinkItem

    from facts_store import Fact

    fact_hits = [
        (
            "identity.brand_name",
            Fact(value="Ciphex", verified_on="2026-08-17", source_url="https://ciphex.io/fact-page", notes=None),
        )
    ]

    @dataclass
    class _FakeRagChunk:
        content: str
        title: str
        date: str
        source_url: str
        slug: str
        kind: str
        score: float

    rag_hit = _FakeRagChunk(
        content="rag content",
        title="RAG Doc",
        date="August 1, 2026",
        source_url="https://ciphex.io/assets/documents/ecosystem-update-aug01-26.pdf",
        slug="ecosystem-update-aug01-26",
        kind="pdf",
        score=0.5,
    )
    page_hit = _FakePageChunk(
        content="page content", title="Page Doc", slug="some-page", score=0.5, page_url="https://ciphex.io/some-page"
    )

    _, _, link_items = build_context(fact_hits, [rag_hit], [page_hit])
    urls_in_order = [item.url for item in link_items]
    rag_idx = urls_in_order.index(rag_hit.source_url)
    page_idx = urls_in_order.index(page_hit.page_url)
    fact_idx = urls_in_order.index("https://ciphex.io/fact-page")
    assert rag_idx < page_idx < fact_idx


# ─────────────────────────── router-level: page hits ───────────────────────────


async def test_page_hit_alone_produces_rag_answer_kind_and_citation(stub_stores, monkeypatch):
    async def fake_retrieve_pages(conn, provider, query, top_k=3, **kwargs):
        return [
            _FakePageChunk(
                content="Ciphex Alpha is a systemized execution and portfolio management product.",
                title="Ciphex Alpha",
                slug="ciphex-alpha",
                score=0.9,
                page_url="https://ciphex.io/ciphex-alpha",
            )
        ]

    async def fake_retrieve(conn, provider, query, top_k=4):
        return []

    monkeypatch.setattr("pubs_rag.retrieval.retrieve_pages", fake_retrieve_pages)
    monkeypatch.setattr("pubs_rag.retrieval.retrieve", fake_retrieve)  # Internal Updates corpus: no hits
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = object()

    response = await answer_question("describe the ciphex alpha product in detail", stub_stores)
    assert response.meta.answer_kind == "rag"
    links = [b for b in response.blocks if b.type == "links"]
    assert links and any("ciphex-alpha" in item.url for item in links[0].items)


async def test_page_hits_below_min_score_do_not_prevent_refusal(stub_stores, monkeypatch):
    from century_core.config import Config

    async def fake_retrieve_pages(conn, provider, query, top_k=3, **kwargs):
        return [
            _FakePageChunk(
                content="barely relevant",
                title="Some Page",
                slug="some-page",
                score=Config.RAG_MIN_SCORE - 0.05,
                page_url="https://ciphex.io/some-page",
            )
        ]

    monkeypatch.setattr("pubs_rag.retrieval.retrieve_pages", fake_retrieve_pages)
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = object()

    response = await answer_question("write me a poem about nothing at all", stub_stores)
    assert response.meta.answer_kind == "refusal"


# ─────────────────────────── router-level: roster short-circuit ───────────────────────────


async def test_who_is_kevin_answers_with_real_content(stub_stores):
    from century_core.qa.pages_roster import get_roster

    if not get_roster().people:
        return  # environment without the harvested corpus checked out

    response = await answer_question("Who is Kevin?", stub_stores)
    assert response.meta.answer_kind == "faq"
    para = next(b for b in response.blocks if b.type == "paragraph")
    assert "Kevin" in para.md
    links = next(b for b in response.blocks if b.type == "links")
    assert links.items[0].url == "https://ciphex.io/leadership-team"


async def test_who_is_leadership_team_answers_with_real_content(stub_stores):
    from century_core.qa.pages_roster import get_roster

    if not get_roster().people:
        return

    response = await answer_question("who is the ciphex leadership team?", stub_stores)
    assert response.meta.answer_kind == "faq"
    para = next(b for b in response.blocks if b.type == "paragraph")
    assert len(para.md) > 20


async def test_steve_martin_does_not_take_the_roster_route(stub_stores):
    # Scope: this asserts the Sprint 3 roster hook specifically did NOT
    # fire for an unknown name -- is_person_question("...Steve Martin",
    # roster) returning False is covered directly in test_pages_roster.py.
    # Whatever the generic facts/RAG/LLM fallback below the roster hook
    # does with this query is pre-existing behavior this branch doesn't
    # own (facts_search.py is another agent's file on this branch) --
    # asserting a full-pipeline "refusal" here would couple this test to
    # that unrelated keyword-overlap-matching behavior instead.
    from century_core.qa.pages_roster import get_roster

    if not get_roster().people:
        return

    response = await answer_question("tell me more about Steve Martin", stub_stores)
    links = [b for b in response.blocks if b.type == "links"]
    cited_urls = {item.url for block in links for item in block.items}
    assert "https://ciphex.io/leadership-team" not in cited_urls
    text_blocks = " ".join(b.md for b in response.blocks if b.type in ("paragraph", "warning"))
    assert "Steve Martin" not in text_blocks  # never fabricated as a real team member
