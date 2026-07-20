import pytest
from pydantic import ValidationError

from century_core.models import (
    FactBlock,
    HeadingBlock,
    InboundCommand,
    InboundMessage,
    ResponseIR,
    ResponseMeta,
)


def test_inbound_message_parses_c1_shape():
    msg = InboundMessage(
        channel="telegram",
        channel_msg_id="123",
        user_ref="u1",
        chat_ref="c1",
        thread_ref=None,
        text="/price",
        command=InboundCommand(name="price", args=""),
        is_dm=False,
        mentioned=True,
        locale="en-US",
        ts="2026-07-20T00:00:00Z",
    )
    assert msg.command.name == "price"


def test_inbound_message_rejects_unknown_channel():
    with pytest.raises(ValidationError):
        InboundMessage(
            channel="carrier-pigeon",
            channel_msg_id="1",
            user_ref="u",
            chat_ref="c",
            text="hi",
            is_dm=True,
            mentioned=True,
            ts="2026-07-20T00:00:00Z",
        )


def test_inbound_message_rejects_extra_fields():
    with pytest.raises(ValidationError):
        InboundMessage(
            channel="telegram",
            channel_msg_id="1",
            user_ref="u",
            chat_ref="c",
            text="hi",
            is_dm=True,
            mentioned=True,
            ts="2026-07-20T00:00:00Z",
            unexpected_field="nope",
        )


def test_response_ir_discriminates_block_types():
    response = ResponseIR(
        blocks=[
            {"type": "heading", "text": "hi"},
            {"type": "fact", "label": "x", "value": "1", "source": "https://a", "as_of": "2026-01-01"},
        ],
        meta=ResponseMeta(answer_kind="command"),
    )
    assert isinstance(response.blocks[0], HeadingBlock)
    assert isinstance(response.blocks[1], FactBlock)


def test_response_ir_rejects_unknown_block_type():
    with pytest.raises(ValidationError):
        ResponseIR(
            blocks=[{"type": "table", "rows": []}],
            meta=ResponseMeta(answer_kind="command"),
        )


def test_response_meta_rejects_unknown_answer_kind():
    with pytest.raises(ValidationError):
        ResponseMeta(answer_kind="vibes")


def test_response_meta_defaults_are_empty_lists():
    meta = ResponseMeta(answer_kind="refusal")
    assert meta.facts_used == []
    assert meta.kpis_used == []
