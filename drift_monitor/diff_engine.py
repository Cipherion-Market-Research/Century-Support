"""Deterministic line-level hunk diffing between a baseline snapshot and a
freshly-fetched, normalized page text. Pure stdlib difflib -- no LLM.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(frozen=True)
class Hunk:
    op: str  # "replace" | "insert" | "delete" (difflib opcode tags; "equal" is never kept)
    old_lines: tuple
    new_lines: tuple

    @property
    def old_text(self) -> str:
        return "\n".join(self.old_lines)

    @property
    def new_text(self) -> str:
        return "\n".join(self.new_lines)


def compute_hunks(old_text: str, new_text: str) -> list[Hunk]:
    """Return the non-equal opcodes from a line-level SequenceMatcher diff,
    in stable document order."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)

    hunks = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        hunks.append(
            Hunk(op=tag, old_lines=tuple(old_lines[i1:i2]), new_lines=tuple(new_lines[j1:j2]))
        )
    return hunks


def unified_diff_text(old_text: str, new_text: str, fromfile: str = "baseline", tofile: str = "current") -> str:
    """Human-readable evidence diff for reports/PR bodies."""
    diff_lines = difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    )
    return "\n".join(diff_lines)
