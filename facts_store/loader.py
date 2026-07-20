"""Loader for facts.yaml — schema validation + orphan-key checking (C4).

See docs/CONTRACTS.md C4 for the frozen schema this enforces.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Union

import yaml
from pydantic import ValidationError

from .exceptions import FactsValidationError
from .schema import ALLOWED_CATEGORIES, Fact, FactsFile

DEFAULT_FACTS_PATH = Path(__file__).resolve().parent.parent / "facts.yaml"

# "<category>.<rest>", category alphanumeric/hyphen (matches round-terms),
# rest may contain letters, digits, underscore, dot, hyphen.
_KEY_RE = re.compile(r"^([a-z][a-z0-9-]*)\.([A-Za-z0-9_.-]+)$")


class _DuplicateKeyLoader(yaml.SafeLoader):
    """SafeLoader that raises on duplicate mapping keys.

    Plain PyYAML silently lets the second value win on a duplicate key,
    which would hide a copy-paste mistake in facts.yaml (two entries
    accidentally sharing one fact key) instead of failing CI.
    """


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen = set()
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise FactsValidationError(
                f"duplicate key {key!r} in facts.yaml (line {key_node.start_mark.line + 1})"
            )
        seen.add(key)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_DuplicateKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _check_key_format(key: str) -> None:
    """Enforce '<category>.<key>' with category in ALLOWED_CATEGORIES.

    This is the "no-orphan-keys" check: it catches typos in the category
    prefix (e.g. "toknomics.max_supply_cpx") that would otherwise silently
    create a fact no category listing or consumer would ever find.
    """
    match = _KEY_RE.match(key)
    if not match:
        raise FactsValidationError(
            f"malformed fact key {key!r} — expected '<category>.<key>' "
            f"(e.g. 'tokenomics.max_supply_cpx')"
        )
    category = match.group(1)
    if category not in ALLOWED_CATEGORIES:
        raise FactsValidationError(
            f"orphaned category prefix {category!r} in fact key {key!r} — "
            f"must be one of {sorted(ALLOWED_CATEGORIES)} (docs/CONTRACTS.md C4)"
        )


def load_facts_file(path: Union[str, Path] = DEFAULT_FACTS_PATH) -> FactsFile:
    """Load and fully validate facts.yaml.

    Runs, in order: YAML parse (with duplicate-key detection), per-key
    category-prefix check ("no orphan keys"), then pydantic schema
    validation of every fact entry (required fields, `version: 1`).

    Raises FactsValidationError on any problem, with a message specific
    enough to fix without re-reading this module.
    """
    path = Path(path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FactsValidationError(f"could not read facts file at {path}: {exc}") from exc

    try:
        raw = yaml.load(raw_text, Loader=_DuplicateKeyLoader)
    except FactsValidationError:
        raise
    except yaml.YAMLError as exc:
        raise FactsValidationError(f"facts.yaml is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise FactsValidationError(
            "facts.yaml must contain a top-level mapping with 'version' and 'facts'"
        )

    facts_raw = raw.get("facts")
    if isinstance(facts_raw, dict):
        for key in facts_raw:
            _check_key_format(key)

    try:
        return FactsFile.model_validate(raw)
    except ValidationError as exc:
        raise FactsValidationError(f"facts.yaml failed schema validation:\n{exc}") from exc


class FactsStore:
    """Read-only accessor over a validated facts.yaml.

    Construct once (directly or via the module-level `default_store()`
    helper) and reuse — this class does not watch the file for changes.
    """

    def __init__(self, facts_file: FactsFile):
        self._facts_file = facts_file

    @classmethod
    def load(cls, path: Union[str, Path] = DEFAULT_FACTS_PATH) -> "FactsStore":
        return cls(load_facts_file(path))

    def get(self, key: str) -> Optional[Fact]:
        """Return the Fact for `key`, or None if the key is absent.

        Per C4 (docs/CONTRACTS.md): a key that is absent OR whose value is
        the `unknown` sentinel means the core service must answer "I don't
        know" plus the official link — callers should check both
        `get(key) is None` and `fact.is_unknown`.
        """
        return self._facts_file.facts.get(key)

    def __contains__(self, key: str) -> bool:
        return key in self._facts_file.facts

    def __len__(self) -> int:
        return len(self._facts_file.facts)

    def keys(self):
        return self._facts_file.facts.keys()

    def by_category(self, category: str) -> dict:
        prefix = f"{category}."
        return {k: v for k, v in self._facts_file.facts.items() if k.startswith(prefix)}


_default_store: Optional[FactsStore] = None


def default_store() -> FactsStore:
    """Process-wide cached FactsStore over the repo-root facts.yaml."""
    global _default_store
    if _default_store is None:
        _default_store = FactsStore.load()
    return _default_store
