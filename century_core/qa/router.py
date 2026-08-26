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
import re
from pathlib import PurePosixPath
from urllib.parse import urlparse

from century_core import guardrails, response_guard
from century_core.commands.contribute import handle_contribute
from century_core.commands.ecosystem import handle_ecosystem
from century_core.commands.price import handle_price
from century_core.config import Config
from century_core.models import LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta
from century_core.qa import facts_search
from century_core.qa.contribution import is_contribution_question
from century_core.qa.holders import answer_holder_question, is_holder_question
from century_core.qa.intro import is_intro_question
from century_core.qa.labels import humanize_fact_key
from century_core.qa.language import is_non_english_question, non_english_response
from century_core.qa.offtopic import is_offtopic_question, offtopic_response
from century_core.qa.price import is_buy_question, is_listing_question, is_price_question
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


# Era-framing for legacy facts (live tester feedback, 2026-08-26): "how many
# months will contributions be permitted?" -> "12 months" -- the LLM
# presented round-terms.legacy_2025_vesting_months (the concluded 2025
# round) as if it described the current Contribution Program. Any fact
# whose key contains "legacy_2025" gets its context line prefixed with an
# explicit era marker so the LLM can never mistake it for current-program
# information, regardless of how the LLM chooses to phrase its answer.
_LEGACY_2025_ERA_MARKER = "[LEGACY 2025 ROUND — CONCLUDED; not the current Contribution Program] "

# Item 4 (token-vs-system disambiguation, live tester feedback, 2026-08-26):
# "can the CPX token do autonomous trading?" (x2) got answers implying the
# CPX token itself trades, because the only grounding fact was
# products.ciphex_alpha_description (the autonomous Alpha system), with
# nothing in context to distinguish "the token" from "the system that
# happens to also be described nearby". When a token/cpx-worded query is
# grounded in that fact, prepend an explicit instruction line so the LLM
# cannot conflate them -- see facts_search.py's "token"/"tokens" -> "stack"
# alias, which pulls identity.product_stack (CPX Token vs Ciphex Alpha as
# separate line items) into the same fact_hits alongside it.
_TOKEN_WORD_TOKENS = {"token", "tokens", "cpx"}
_ALPHA_DESCRIPTION_KEY = "products.ciphex_alpha_description"
_DISAMBIG_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TOKEN_VS_SYSTEM_NOTE = (
    "[NOTE: CPX is the ecosystem token; Ciphex Alpha is the autonomous system "
    "— do not attribute Alpha's capabilities to the token itself]"
)

# Item 3 (link relevance, live tester feedback, 2026-08-26): every fact_hit
# facts_search returns already enters the LLM's context (see the loop
# below) -- there's no "did this fact's line actually reach the LLM"
# distinction to gate on. What tester transcripts actually showed was
# coincidental TIE matches riding along as citation links purely because
# they placed in the top-`limit` (e.g. atlas-rwa-services on "who is the
# CPX management team?", financing-activities on "dynamic risk
# management") despite scoring far below the fact that actually answers
# the question. A fact still informs the LLM's context regardless of its
# score (more grounding rarely hurts), but only earns a citation LINK --
# which readers read as an endorsement of relevance -- when it scores at
# least this fraction of the top-scoring fact_hit's score.
_LINK_RELEVANCE_RATIO = 0.5


def _fact_context_line(key: str, fact) -> str:
    line = f"[{key}] {fact.value} (verified {fact.verified_on}, source {fact.source_url})"
    if "legacy_2025" in key:
        line = _LEGACY_2025_ERA_MARKER + line
    return line


def build_context(fact_hits, rag_hits, *, linkable_fact_keys=None, query=""):
    """Compose the LLM context string, the facts_used list, and the
    deduped citation link list from fact/RAG hits. Split out from
    answer_question for direct unit testing (era-framing regression) --
    see _fact_context_line above and the link-dedup note below.

    `linkable_fact_keys`: optional set of fact keys allowed to produce a
    citation link (item 3 -- see _LINK_RELEVANCE_RATIO above); every
    fact_hit still becomes a context line regardless. None (the default)
    means "no filtering", i.e. every fact_hit is linkable -- existing
    callers that don't compute a relevance threshold keep today's
    behavior.

    `query`: the original question text, used only for item 4's
    token-vs-system disambiguation note (see _TOKEN_VS_SYSTEM_NOTE above).
    Defaults to "" (no note) so existing callers are unaffected.
    """
    context_parts = []
    facts_used = []
    fact_links = []
    rag_links = []

    query_tokens = set(_DISAMBIG_TOKEN_RE.findall(query.lower()))
    query_has_token_word = bool(query_tokens & _TOKEN_WORD_TOKENS)

    for key, fact in fact_hits:
        context_parts.append(_fact_context_line(key, fact))
        facts_used.append(key)
        if key == _ALPHA_DESCRIPTION_KEY and query_has_token_word:
            context_parts.insert(0, _TOKEN_VS_SYSTEM_NOTE)
        # Never link fact.source_url verbatim (production audit,
        # 2026-08-18): many facts.yaml source_url values are internal
        # provenance notes, not user-facing links -- the literal string
        # "internal://content-audit-2026-07-20" was rendering as an
        # unclickable citation. Only cite it when it's a real, allowlisted
        # public URL; otherwise the fact still informs the LLM's context
        # above, it's just never turned into a link.
        if linkable_fact_keys is not None and key not in linkable_fact_keys:
            continue
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
    # truncated link list by fact links appended after it. Deduped by URL
    # across the COMBINED list (live tester feedback, 2026-08-26: the same
    # URL showed up twice -- e.g. a fact link and a RAG link both pointing
    # at the same page -- because each list was only deduped internally,
    # never against each other) before any truncation happens downstream.
    link_items = []
    seen_urls = set()
    for item in rag_links + fact_links:
        if item.url not in seen_urls:
            link_items.append(item)
            seen_urls.add(item.url)

    context = "\n\n".join(context_parts)
    return context, facts_used, link_items


async def answer_question(question: str, stores) -> ResponseIR:
    # Non-English input gate (live tester feedback, 2026-08-19): a Mandarin
    # message got a confused English reply -- the facts+RAG+LLM path (and
    # every deterministic route below) has no way to handle a non-English
    # question, so this is checked FIRST, before even offtopic. See
    # qa/language.py.
    if is_non_english_question(question):
        return response_guard.enforce_response(non_english_response())

    # Greetings/smalltalk/off-topic short-circuit (go-live incident
    # 2026-08-17): "write me a poem" must never reach facts search or the
    # LLM at all -- see qa/offtopic.py.
    if is_offtopic_question(question):
        return response_guard.enforce_response(offtopic_response())

    if is_supply_question(question):
        return await answer_supply_question(stores, question)

    # Owner ruling 2026-08-17: price questions ("what's the price of CPX",
    # "how much does CPX cost") always get the same deterministic /price
    # response -- CPX has no market price to quote, and this is exactly
    # the free-form path that could otherwise invent or leak a banned
    # figure. Checked after is_supply_question so a query like "total
    # supply" is never misrouted here. Listing intent ("when does ciphex
    # start trading on exchanges") and buy intent ("how do I buy CPX" --
    # live tester feedback, 2026-08-19: this fell through to RAG and served
    # a 2025-era update's stale listing claim, the worst answer surfaced in
    # that test pass) get the same deterministic answer -- see qa/price.py.
    if is_price_question(question) or is_listing_question(question) or is_buy_question(question):
        return await handle_price("", stores)

    # Contribution-program-intent questions ("when can I contribute?", "how
    # long will the contribution program run?" -- live tester feedback,
    # 2026-08-26): five near-identical-intent questions got one good
    # answer, three refusals, and one flat-wrong answer from facts_search +
    # LLM ranking. Checked after price/listing/buy (a buy-intent question
    # like "how do I buy CPX" keeps its existing /price route even where it
    # overlaps contribution vocabulary) and before holders -- see
    # qa/contribution.py.
    if is_contribution_question(question):
        return await handle_contribute("", stores)

    # Holder-count questions ("how many holders does CPX have") -- checked
    # after is_price_question/is_supply_question (same reasoning: a query
    # like "total supply" must never be misrouted here), before facts
    # search/RAG since neither has a real answer for this -- see
    # qa/holders.py.
    if is_holder_question(question):
        return response_guard.enforce_response(await answer_holder_question(stores))

    # Intro-intent questions ("what is cipex", "tell me about CipheX" --
    # live tester feedback, 2026-08-19) route to the existing deterministic
    # ecosystem overview instead of RAG, which had been producing unapproved
    # paraphrases citing old PDFs. Checked after supply/price/listing/buy/
    # holders so a more specific route always wins on overlap (e.g. "what is
    # the total supply" stays a supply question) -- see qa/intro.py.
    if is_intro_question(question):
        return response_guard.enforce_response(await handle_ecosystem("", stores))

    scored_fact_hits = facts_search.search_facts_scored(stores.facts, question, limit=3)
    fact_hits = [(key, fact) for _, key, fact in scored_fact_hits]
    rag_hits = await _rag_search(stores, question)

    if not fact_hits and not rag_hits:
        return response_guard.safe_refusal()

    # Item 3 (link relevance): a fact_hit only earns a citation link if it
    # scores within _LINK_RELEVANCE_RATIO of the top-scoring fact_hit --
    # see build_context's linkable_fact_keys docstring above. scored_fact_hits
    # is non-empty and sorted highest-first whenever fact_hits is non-empty.
    top_score = scored_fact_hits[0][0] if scored_fact_hits else 0.0
    linkable_fact_keys = {
        key for score, key, _ in scored_fact_hits if top_score > 0 and score >= _LINK_RELEVANCE_RATIO * top_score
    }

    context, facts_used, link_items = build_context(
        fact_hits, rag_hits, linkable_fact_keys=linkable_fact_keys, query=question
    )
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
