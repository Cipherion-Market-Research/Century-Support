"""Pydantic schema for facts.yaml (C4, docs/CONTRACTS.md)."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

# Category prefixes allowed in a fact key, per C4: a key is
# "<category>.<rest>" where <category> must be one of these.
ALLOWED_CATEGORIES = frozenset(
    {
        "identity",
        "contracts",
        "round-terms",
        "tokenomics",
        "products",
        "links",
        "legal",
    }
)

UNKNOWN = "unknown"


class Fact(BaseModel):
    """A single canonical fact entry."""

    model_config = ConfigDict(extra="forbid")

    value: Any
    verified_on: date
    source_url: str
    notes: str | None = None

    @field_validator("source_url")
    @classmethod
    def _source_url_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "source_url must not be blank — every fact needs provenance (C4)"
            )
        return v

    @property
    def is_unknown(self) -> bool:
        """True if this fact's value is the `unknown` sentinel (C4).

        Per docs/CONTRACTS.md: a key that is absent or `unknown` means core
        must answer "I don't know" plus the official link, never a guess.
        """
        return self.value == UNKNOWN


class FactsFile(BaseModel):
    """Top-level facts.yaml document."""

    model_config = ConfigDict(extra="forbid")

    version: int
    facts: dict[str, Fact]

    @field_validator("version")
    @classmethod
    def _version_is_1(cls, v: int) -> int:
        if v != 1:
            raise ValueError(
                f"unsupported facts.yaml schema version: {v!r} (only version 1 is defined)"
            )
        return v
