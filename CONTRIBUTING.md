# Contributing

## `facts.yaml` — canonical facts store

`facts.yaml` is the single source of truth the bot uses for numeric and
identity answers (contract addresses, round terms, tokenomics, official
emails/links, product descriptions, legal posture). Its schema is frozen as
contract **C4** in `docs/CONTRACTS.md`.

**`facts.yaml` changes only by reviewed pull request. No process — including
the nightly drift checker — writes to this file automatically.** The
drift checker's job is to *propose* changes (as a PR or notification) when
live site copy disagrees with `facts.yaml`; a human always reviews before
merge.

### Rules for every fact

- Every fact needs `value`, `verified_on` (the date you confirmed it),
  and `source_url` (where you confirmed it) — no exceptions. `notes` is
  optional but strongly encouraged when the provenance isn't a straight
  page-read (e.g. it came from a cross-repo audit, or two sources disagree).
- If you cannot verify a fact — especially an **identity** fact like a
  support email, a canonical domain, or whether something is "live" — set
  `value: unknown`. Never guess. An absent or `unknown` fact means the bot
  answers "I don't know" plus the official link; a wrong guess is worse
  than that.
- Fact keys are `<category>.<key>`, where `<category>` is one of:
  `identity`, `contracts`, `round-terms`, `tokenomics`, `products`, `links`,
  `legal`. A typo'd category prefix (e.g. `toknomics.max_supply_cpx`) is an
  orphan key and will fail CI — see below.
- Prefer citing the most direct source available. If a fact is only
  confirmed via cross-repo research (not a page you can point a browser at
  in this repo's `data/kb_source/` corpus), say so explicitly in `notes` and
  flag it for a follow-up live-site spot-check.

### Adding or changing a fact

1. Edit `facts.yaml` directly — it's a flat YAML mapping, so most changes
   are a small, easy-to-review diff.
2. Run the validator locally before opening a PR:

   ```bash
   pip install pydantic PyYAML
   python scripts/validate_facts.py
   python -m pytest tests/test_facts_store.py -v
   ```

3. Open a PR. CI (`.github/workflows/facts-ci.yml`) re-runs the same
   checks automatically on any PR touching `facts.yaml` or `facts_store/`.
4. The project owner reviews the PR against the underlying source before
   merging — this is the review gate the schema's provenance fields exist
   to support.

### What CI actually checks

`scripts/validate_facts.py` (also exercised by `tests/test_facts_store.py`)
enforces:

- **Schema** — `version: 1`, and every fact has `value` + `verified_on` +
  non-blank `source_url`, with no extra/unrecognized fields.
- **No orphan keys** — every fact key's category prefix is one of the
  seven C4 categories.
- **No duplicate keys** — the YAML loader rejects two entries for the same
  fact key instead of silently letting the second one win.

### Using facts.yaml in code

```python
from facts_store import default_store

store = default_store()
fact = store.get("tokenomics.max_supply_cpx")
if fact is None or fact.is_unknown:
    ...  # "I don't know" + official link — never fall back to a guess
else:
    fact.value, fact.source_url, fact.verified_on
```

See `facts_store/__init__.py` for the full accessor API.
