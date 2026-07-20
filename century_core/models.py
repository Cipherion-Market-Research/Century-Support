"""C1 (adapter -> core) and C2 (core -> adapter) pydantic models.

Verbatim from docs/CONTRACTS.md (FROZEN). Field names/shapes here must not
change without an owner-approved contract version bump — raise it to the
owner, never edit unilaterally.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────── C1: inbound message ───────────────────────────


class InboundCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    args: str = ""


class InboundMessage(BaseModel):
    """C1 message envelope every channel adapter POSTs to /v1/messages.

    `command` is non-null only when the platform natively parsed a command;
    core also detects command-like text itself (see commands/registry.py).
    """

    model_config = ConfigDict(extra="forbid")

    channel: Literal["telegram", "discord", "slack", "x"]
    channel_msg_id: str
    user_ref: str
    chat_ref: str
    thread_ref: Optional[str] = None
    text: str
    command: Optional[InboundCommand] = None
    is_dm: bool
    mentioned: bool
    locale: Optional[str] = None
    ts: str


# ─────────────────────────── C2: response blocks ───────────────────────────


class HeadingBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["heading"] = "heading"
    text: str


class ParagraphBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["paragraph"] = "paragraph"
    md: str


class FactBlock(BaseModel):
    """Hard rule (C2): value/source/as_of come from the stores verbatim —
    never author these from LLM output."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["fact"] = "fact"
    label: str
    value: str
    source: str
    as_of: str


class LinkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    url: str


class LinksBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["links"] = "links"
    items: list[LinkItem]


class WarningBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["warning"] = "warning"
    md: str


class ButtonsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["buttons"] = "buttons"
    items: list[LinkItem]


Block = Annotated[
    Union[HeadingBlock, ParagraphBlock, FactBlock, LinksBlock, WarningBlock, ButtonsBlock],
    Field(discriminator="type"),
]

AnswerKind = Literal["command", "faq", "rag", "llm", "refusal"]


class ResponseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer_kind: AnswerKind
    facts_used: list[str] = Field(default_factory=list)
    kpis_used: list[str] = Field(default_factory=list)


class ResponseIR(BaseModel):
    """C2 response IR core replies with."""

    model_config = ConfigDict(extra="forbid")
    blocks: list[Block]
    meta: ResponseMeta


# ───────────────────────── /v1/facts/:key response ─────────────────────────


class FactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    known: Literal[True] = True
    value: object
    verified_on: str
    source_url: str
    notes: Optional[str] = None


class UnknownFactResponse(BaseModel):
    """C4: a key that is absent or `unknown` -> "I don't know" + official link."""

    model_config = ConfigDict(extra="forbid")
    key: str
    known: Literal[False] = False
    message: str
    official_link: str


# ───────────────────────────── /v1/broadcasts ──────────────────────────────


class BroadcastTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Optional[Literal["telegram", "discord", "slack", "x"]] = None  # None = every channel
    chat_ref: Optional[str] = None  # None = every configured chat on that channel


class BroadcastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[Block]
    target: BroadcastTarget = Field(default_factory=BroadcastTarget)


class BroadcastAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    broadcast_id: str
    enqueued: bool
    queued_at: str
