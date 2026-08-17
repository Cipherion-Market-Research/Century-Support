"""Human-readable link labels for facts.yaml keys.

Go-live incident 2026-08-17: the Q&A router was building citation
`LinkItem.label` directly from the raw dotted fact key (e.g.
"tokenomics.onchain_total_supply_eth"), so a user asking a follow-up
question saw the internal storage key as a clickable link's visible text.
A dotted, underscored, snake_case string must never reach an end user --
this module renders something a human would actually read instead.
"""
import re

# Small explicit map for keys whose mechanical (segment -> title-case)
# transform would still read awkwardly, or where a specific phrasing is
# worth pinning down. Checked before the generic fallback below.
_EXPLICIT_LABELS = {
    "tokenomics.onchain_total_supply_eth": "CPX Total Supply (Ethereum)",
    "tokenomics.fy2026_fd_supply": "CPX Effective Supply",
    "tokenomics.max_supply_cpx": "CPX Max Supply",
    "contracts.cpx_token_ethereum": "CPX Token Contract",
    "contracts.cpx_claiming_ethereum": "CPX Claiming Contract",
    "identity.listing_initiative": "Listing Roadmap",
    "links.token_page": "CPX Token Page",
}

# Segment words that should render upper-case rather than title-case when
# the generic fallback builds a label mechanically.
_ACRONYMS = {"cpx", "erc", "usd", "eth", "apy", "apr", "url", "fy", "fd", "dex", "cex", "sa", "id"}

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


def humanize_fact_key(key: str) -> str:
    """Render a facts.yaml dotted key as a human-readable link label.

    Never returns the raw key: falls back to a mechanical transform of the
    key's final dotted segment (underscores -> spaces, each word
    title-cased, known acronyms upper-cased) when there's no explicit
    override.
    """
    if key in _EXPLICIT_LABELS:
        return _EXPLICIT_LABELS[key]

    segment = key.rsplit(".", 1)[-1]
    words = _WORD_RE.findall(segment)
    if not words:
        # Should be unreachable given facts_store's key-format validation
        # (every key is "<category>.<rest>"), but never fall through to
        # the raw key regardless.
        return "Ciphex"

    rendered = [w.upper() if w.lower() in _ACRONYMS else w.capitalize() for w in words]
    return " ".join(rendered)
