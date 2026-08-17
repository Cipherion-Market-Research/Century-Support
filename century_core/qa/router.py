"""Q&A routing: facts.yaml keyword match + pubs_rag RAG (publications only)
-> guarded LLM phrasing -> C2 response, with a deterministic escape hatch
for the supply on-chain-vs-effective question (see supply.py) and a hard
refusal when nothing relevant is found.

WP-5 brief item 2: page-level/identity/numeric questions answer from
facts.yaml, not RAG; the RAG corpus is the 12 publications only (WP-4
scope decision — see pubs_rag/ingest.py).
"""
from century_core import guardrails, response_guard
from century_core.commands.price import handle_price
from century_core.config import Config
from century_core.models import LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta
from century_core.qa import facts_search
from century_core.qa.price import is_price_question
from century_core.qa.supply import answer_supply_question, is_supply_question


async def _rag_search(stores, question: str):
    if stores.rag_conn is None or stores.rag_provider is None:
        return []
    from pubs_rag.retrieval import retrieve

    hits = await retrieve(stores.rag_conn, stores.rag_provider, question, top_k=Config.RAG_TOP_K)
    return [h for h in hits if h.score >= Config.RAG_MIN_SCORE]


async def answer_question(question: str, stores) -> ResponseIR:
    if is_supply_question(question):
        return await answer_supply_question(stores)

    # Owner ruling 2026-08-17: price questions ("what's the price of CPX",
    # "how much does CPX cost") always get the same deterministic /price
    # response -- CPX has no market price to quote, and this is exactly
    # the free-form path that could otherwise invent or leak a banned
    # figure. Checked after is_supply_question so a query like "total
    # supply" is never misrouted here.
    if is_price_question(question):
        return await handle_price("", stores)

    fact_hits = facts_search.search_facts(stores.facts, question, limit=3)
    rag_hits = await _rag_search(stores, question)

    if not fact_hits and not rag_hits:
        return response_guard.safe_refusal()

    context_parts = []
    facts_used = []
    fact_links = []
    rag_links = []

    for key, fact in fact_hits:
        context_parts.append(f"[{key}] {fact.value} (verified {fact.verified_on}, source {fact.source_url})")
        facts_used.append(key)
        fact_links.append(LinkItem(label=key, url=fact.source_url))

    seen_rag_urls = set()
    for hit in rag_hits:
        context_parts.append(f"[{hit.slug}] {hit.content} (source {hit.source_url}, {hit.date})")
        # retrieve() returns top-K CHUNKS, not top-K distinct documents --
        # dedupe so one publication with several matching chunks doesn't
        # show up as 3 identical citations.
        if hit.source_url not in seen_rag_urls:
            rag_links.append(LinkItem(label=hit.title, url=hit.source_url))
            seen_rag_urls.add(hit.source_url)

    # RAG links first: when rag_hits exist, answer_kind is "rag" (RAG is the
    # primary source) -- its citation must never be crowded out of the
    # truncated link list by fact links appended after it.
    link_items = rag_links + fact_links

    context = "\n\n".join(context_parts)
    # Everything the LLM is allowed to state a number about is whatever's
    # literally in the context handed to it -- not link labels (fact keys
    # like "legacy_2025_vesting_months" embed digits that are naming
    # convention, not factual claims) and not fact/rag metadata that never
    # reaches the model.
    allowed_numbers = guardrails.extract_numbers(context)

    raw_answer = await stores.llm.generate(question, context)

    provenance = guardrails.check_numeric_provenance(raw_answer, allowed_numbers)
    if not provenance.ok:
        return response_guard.safe_refusal()

    blocks = [ParagraphBlock(md=raw_answer)]
    if link_items:
        blocks.append(LinksBlock(items=link_items[:3]))

    # "llm" (an ungrounded, context-free answer) is intentionally never
    # produced by this router -- every LLM call here is grounded in at
    # least one fact or RAG hit, or the request is refused above.
    answer_kind = "rag" if rag_hits else "faq"

    response = ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind=answer_kind, facts_used=facts_used, kpis_used=[]),
    )
    # Structural-only final gate (solicitation/APY/price-ban) -- numeric
    # provenance was already checked above against the true LLM output,
    # not the fully-rendered response (whose link labels can carry
    # unrelated digits, as above).
    return response_guard.enforce_response(response)
