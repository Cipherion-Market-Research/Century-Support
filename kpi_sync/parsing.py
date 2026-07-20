"""Small, dependency-free parsing helpers shared by the pollers."""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

# Two-pass conversion so acronym runs (e.g. "totalCPXPresold") collapse
# into one word ("total_cpx_presold") instead of one underscore per
# capital letter ("total_c_p_x_presold").
_CAMEL_RE1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_RE2 = re.compile(r"([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    s1 = _CAMEL_RE1.sub(r"\1_\2", name)
    return _CAMEL_RE2.sub(r"\1_\2", s1).lower()


def parse_upstream_datetime(raw: Optional[str]) -> Optional[str]:
    """Best-effort parse of an upstream timestamp into ISO-8601.

    Returns None (never raises) when the format isn't recognized — an
    unparsed provenance field must become an honest null, not a guess.
    """
    if not raw:
        return None
    raw = raw.strip()

    # Already ISO-8601 with an explicit UTC marker -- pass through verbatim
    # rather than round-tripping it through strptime/strftime.
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            datetime.strptime(raw, fmt)
            return raw
        except ValueError:
            continue

    # Loose "M-D-YYYY h:mm AM/PM" / "M-D-YY h:mm AM/PM" seen on the
    # Sheets-backed ams.ciphex.io fields. No timezone is given, so the
    # result is left naive rather than guessing UTC.
    for fmt in ("%m-%d-%Y %I:%M %p", "%m-%d-%y %I:%M %p"):
        try:
            return datetime.strptime(raw, fmt).isoformat()
        except ValueError:
            continue
    return None


def parse_sheet_response(data: Dict[str, Any]) -> List[dict]:
    """Parse a Google-Sheets-shaped {range, majorDimension, values} payload
    into a list of row dicts keyed by the header row.

    Sheets trims trailing empty cells, so short rows are padded with None
    rather than zip() silently dropping the missing trailing columns.
    """
    values = data.get("values") or []
    if not values:
        return []
    header, *rows = values
    parsed = []
    for row in rows:
        padded = list(row) + [None] * (len(header) - len(row))
        parsed.append(dict(zip(header, padded[: len(header)])))
    return parsed
