#!/usr/bin/env python3
"""CI check for facts.yaml (WP-2, docs/CONTRACTS.md C4).

Validates:
  1. facts.yaml parses as YAML with no duplicate keys.
  2. Every fact key is "<category>.<key>" with category in the C4-frozen
     category list — the "no-orphan-keys" check.
  3. Every fact entry matches the C4 schema: value, verified_on (date),
     source_url (non-blank), optional notes — no extra/unknown fields.
  4. `version: 1` at the document root.

Exits 0 and prints a summary on success; exits 1 and prints every problem
found on failure (does not stop at the first error where avoidable).

Usage:
    python scripts/validate_facts.py [path/to/facts.yaml]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from facts_store import FactsValidationError, load_facts_file  # noqa: E402
from facts_store.loader import DEFAULT_FACTS_PATH  # noqa: E402


def main() -> int:
    facts_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FACTS_PATH

    if not facts_path.exists():
        print(f"FAIL: no facts file at {facts_path}", file=sys.stderr)
        return 1

    try:
        facts_file = load_facts_file(facts_path)
    except FactsValidationError as exc:
        print(f"FAIL: {facts_path} failed validation:\n\n{exc}", file=sys.stderr)
        return 1

    unknown_count = sum(1 for f in facts_file.facts.values() if f.is_unknown)
    categories = sorted({k.split(".", 1)[0] for k in facts_file.facts})

    print(f"OK: {facts_path} is valid (schema version {facts_file.version})")
    print(f"  {len(facts_file.facts)} facts across {len(categories)} categories: {', '.join(categories)}")
    print(f"  {unknown_count} fact(s) explicitly marked unknown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
