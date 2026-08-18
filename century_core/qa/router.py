"""Q&A routing: facts.yaml keyword match + pubs_rag RAG (Internal Updates
only) -> guarded LLM phrasing -> C2 response, with a deterministic escape
hatch for the supply on-chain-vs-effective question (see supply.py) and a
hard refusal when nothing relevant is found.

WP-5 brief item 2: page-level/identity/numeric questions answer from
facts.yaml, not RAG. Corpus policy (Bot Parameter Requirements, 2026-08-18):
the RAG corpus is Internal Updates only -- the Insights & Publications
section is excluded entirely (see pubs_rag/config.py's
SERVE_INSIGHTS_AND_PUBLICATIONS). _is_excluded_rag_source below is a
citation-level backstop against that policy, independent of what's actually
in the retrieval index (e.g. a document ingested before this policy landed
and still sitting in Postgres).
"""
from pathlib import PurePosixPath
from urllib.parse import urlparse

from century_core import guardrails, response_guard
from century_core.commands.price import handle_price
from century_core.config import Config
from century_core.models import LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta
from century_core.qa import facts_search
from century_core.qa.holders import answer_holder_question, is_holder_question
from century_core.qa.labels import humanize_fact_key
from century_core.qa.offtopic import is_offtopic_question, offtopic_response
from century_core.qa.price import is_price_question
from century_core.qa.supply import answer_supply_question, is_supply_question

# Corpus policy backstop (2026-08-18): no citation link may ever point at
# the excluded Insights & Publications section, however it got into
# rag_hits. Two shapes: the page itself, or one of its PDF assets under
# /assets/documents/ -- identified by NOT matching the internal-updates
# "ecosystem-update-*" slug naming convention (the only approved RAG
# source; see pubs_rag/webhook.py's source_url construction).
_PUBLICATIONS_PATH_MARKERS = ("/insights-and-publications", "/ecosystem-publications")
_APPROVED_ASSET_SLUG_PREFIX = "ecosystem-update-"


def _is_excluded_rag_source(url: str) -> bool:
    path = urlparse(url).path
    if any(marker in path for marker in _PUBLICATIONS_PATH_MARKERS):
        return True
    if path.startswith("/assets/documents/"):
        slug = PurePosixPath(path).stem
        if not slug.startswith(_APPROVED_ASSET_SLUG_PREFIX):
            return True
    return False


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

    # Holder-count questions ("how many holders does CPX have") -- checked
    # after is_price_question/is_supply_question (same reasoning: a query
    # like "total supply" must never be misrouted here), before facts
    # search/RAG since neither has a real answer for this -- see
    # qa/holders.py.
    if is_holder_question(question):
        return response_guard.enforce_response(await answer_holder_question(stores))

    # Greetings/smalltalk/off-topic short-circuit (go-live incident
    # 2026-08-17): "write me a poem" must never reach facts search or the
    # LLM at all -- see qa/offtopic.py.
    if is_offtopic_question(question):
        return response_guard.enforce_response(offtopic_response())

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
        # Never link fact.source_url verbatim (production audit,
        # 2026-08-18): many facts.yaml source_url values are internal
        # provenance notes, not user-facing links -- the literal string
        # "internal://content-audit-2026-07-20" was rendering as an
        # unclickable citation. Only cite it when it's a real, allowlisted
        # public URL; otherwise the fact still informs the LLM's context
        # above, it's just never turned into a link.
        if fact.source_url.startswith(Config.ALLOWED_LINK_PREFIXES):
            fact_links.append(LinkItem(label=humanize_fact_key(key), url=fact.source_url))

    seen_rag_urls = set()
    for hit in rag_hits:
        context_parts.append(f"[{hit.slug}] {hit.content} (source {hit.source_url}, {hit.date})")
        # retrieve() returns top-K CHUNKS, not top-K distinct documents --
        # dedupe so one publication with several matching chunks doesn't
        # show up as 3 identical citations. Never cite an excluded
        # Insights & Publications source (see _is_excluded_rag_source).
        if hit.source_url not in seen_rag_urls and not _is_excluded_rag_source(hit.source_url):
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

    # Go-live incident 2026-08-17: fact/RAG hits existed for the *question's
    # tokens* even when the LLM correctly answered "I don't know" (e.g.
    # "write me a poem" partially token-matched unrelated publications).
    # Attaching those citations dressed an honest non-answer up as a
    # sourced one and leaked irrelevant links. When the raw LLM output is
    # itself a refusal/unknown-style non-answer, return it as-is with a
    # single official-site link and NO fact/RAG citations -- checked before
    # the numeric-provenance gate since a refusal like "I don't know how to
    # create a poem." trivially has no numbers to check anyway.
    if guardrails.is_unknown_answer(raw_answer):
        response = ResponseIR(
            blocks=[
                ParagraphBlock(md=raw_answer),
                LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]),
            ],
            meta=ResponseMeta(answer_kind="refusal", facts_used=[], kpis_used=[]),
        )
        return response_guard.enforce_response(response)

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
