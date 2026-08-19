"""Date parsing for the serving recency cutoff (positioning-freshness
policy, owner feedback 2026-08-19) -- see Config.SERVE_DOCS_SINCE in
pubs_rag/config.py for the full policy rationale.

documents.date is TEXT: a free-text display string an ingested PDF's
metadata carries verbatim (e.g. "July 25, 2026", "May 08, 2026" -- see
pubs_rag/db.py's DDL and data/kb_source/inventory.json), not a native
Postgres date column. That means the cutoff comparison happens here in
Python rather than as a SQL WHERE clause: a raw-SQL to_date()-style cast
would throw (and abort the whole query, for every caller) on any document
whose date string doesn't match the expected format -- the opposite of the
"treat unparseable dates conservatively, as excluded" policy this module
implements. If documents.date ever becomes a real `date`/`timestamptz`
column, this module (and its callers) should be retired in favor of a plain
SQL WHERE clause.
"""
from datetime import date, datetime

# Tried in order. "%B %d, %Y" covers every human-authored display date the
# corpus currently uses ("July 25, 2026", "May 08, 2026" -- %d is lenient
# about a leading zero either way). "%Y-%m-%d" is a defensive fallback: a
# few insights-and-publications registry entries in inventory.json already
# use this ISO shape for `date`, even though that section is excluded from
# serving by a separate policy (SERVE_INSIGHTS_AND_PUBLICATIONS).
DATE_FORMATS = ("%B %d, %Y", "%Y-%m-%d")


def parse_document_date(raw: str | None) -> date | None:
    """Best-effort parse of a documents.date display string.

    Returns None for missing/blank/unparseable input -- callers must treat
    None as "exclude, don't guess" per the serving recency cutoff policy,
    not as "no opinion, let it through"."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_cutoff(raw: str | None) -> date | None:
    """Parse an ISO (YYYY-MM-DD) cutoff boundary, e.g. Config.SERVE_DOCS_SINCE.
    Empty/None means "cutoff disabled" -> returns None (the caller's signal
    to skip filtering entirely, not "everything is before an unset date")."""
    if not raw:
        return None
    return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
