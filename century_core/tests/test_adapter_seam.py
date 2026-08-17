"""adapter <-> core seam test (golive-p2, gap #1).

Today nothing tests the real seam between telegram_adapter and
century_core: the adapter's own suite mocks core (test_core_client.py,
test_webhook.py), and century_core's suite hand-synthesizes C1 envelopes
(test_routes.py's BASE_MESSAGE). The C1 contract is therefore asserted
twice, independently, and can drift on either side without either suite
noticing.

This test lives in century_core/tests/ (not telegram_adapter/tests/) so it
gets century_core's conftest fixtures (fake_redis/stub_stores, the same
TestClient wiring as test_routes.py). Importing telegram_adapter from here
is fine -- century_core's suite is run from the repo root (see
telegram_adapter/tests/test_commands_sync.py, which imports
century_core.commands.registry the same way in the other direction) and
telegram_adapter.envelope / telegram_adapter.markdown are both pure,
dependency-free modules (stdlib only -- no python-telegram-bot import at
module scope), so no adapter config/env setup is needed to import them.

Flow, real code on both sides, no hand-built envelopes:
  1. A raw Telegram webhook "Update" JSON dict (shaped like
     telegram_adapter/tests/test_envelope.py's fixtures).
  2. telegram_adapter.envelope.translate_update() -- the REAL adapter
     translation -- turns it into a C1 envelope dict.
  3. POST that envelope verbatim to the REAL century_core FastAPI app
     (TestClient, stub_stores fixture -- no real Redis/Postgres/OpenAI).
  4. Assert a well-formed C2 ResponseIR back.
  5. telegram_adapter.markdown.render_blocks() -- the REAL renderer --
     renders those C2 blocks; assert it renders without error and
     produces non-empty MarkdownV2 output.

Plus one negative: unaddressed group chatter, which the adapter's own
mention gate must filter before anything is ever sent to core.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from century_core.deps import get_stores
from century_core.routes import broadcasts, facts, health, messages
from telegram_adapter.envelope import translate_update
from telegram_adapter.markdown import render_blocks

BOT_USERNAME = "CenturyBot"


@pytest.fixture
def client(stub_stores):
    app = FastAPI()
    app.include_router(messages.router)
    app.include_router(facts.router)
    app.include_router(broadcasts.router)
    app.include_router(health.router)
    app.dependency_overrides[get_stores] = lambda: stub_stores
    with TestClient(app) as c:
        yield c


def _update(message: dict) -> dict:
    return {"update_id": 1, "message": message}


def _command_entity(text: str) -> dict:
    command_token = text.split(" ", 1)[0]
    return {"type": "bot_command", "offset": 0, "length": len(command_token)}


def _mention_entity(text: str) -> dict:
    needle = f"@{BOT_USERNAME}"
    offset = text.index(needle)
    return {"type": "mention", "offset": offset, "length": len(needle)}


def _assert_well_formed_c2(body: dict) -> None:
    """Structural checks on a /v1/messages response body, independent of
    century_core's own pydantic validation (which already ran server-side
    -- this re-checks the shape a channel adapter itself relies on)."""
    assert "blocks" in body and isinstance(body["blocks"], list) and len(body["blocks"]) >= 1
    assert "meta" in body
    assert body["meta"]["answer_kind"] in ("command", "faq", "rag", "llm", "refusal")
    for block in body["blocks"]:
        assert "type" in block


def _assert_renders_nonempty_markdownv2(c2_body: dict) -> None:
    rendered = render_blocks(c2_body)
    assert len(rendered) >= 1
    assert any(part.text.strip() for part in rendered), "renderer produced only empty message parts"


# ───────────────────────── private chat: native /price command ─────────────────────────


def test_private_price_command_round_trips_through_real_adapter_and_core(client):
    text = "/price"
    message = {
        "message_id": 10,
        "from": {"id": 111, "username": "alice", "language_code": "en"},
        "chat": {"id": 111, "type": "private"},
        "date": 1753600000,
        "text": text,
        "entities": [_command_entity(text)],
    }

    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)
    assert envelope is not None
    assert envelope["command"] == {"name": "price", "args": ""}

    resp = client.post("/v1/messages", json=envelope)
    assert resp.status_code == 200
    body = resp.json()
    _assert_well_formed_c2(body)
    assert body["meta"]["answer_kind"] == "command"
    assert body["blocks"][0]["text"] == "CPX Price"

    _assert_renders_nonempty_markdownv2(body)


# ───────────────────────── group chat: addressed mention ─────────────────────────


def test_group_mention_round_trips_through_real_adapter_and_core(client):
    text = f"@{BOT_USERNAME} what is the total supply of CPX?"
    message = {
        "message_id": 20,
        "from": {"id": 222, "username": "bob"},
        "chat": {"id": -1001234, "type": "supergroup"},
        "date": 1753600000,
        "text": text,
        "entities": [_mention_entity(text)],
    }

    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)
    assert envelope is not None
    assert envelope["is_dm"] is False
    assert envelope["mentioned"] is True

    resp = client.post("/v1/messages", json=envelope)
    assert resp.status_code == 200
    body = resp.json()
    _assert_well_formed_c2(body)
    # Deterministic: both tokenomics.onchain_total_supply_eth and
    # tokenomics.fy2026_fd_supply are known (non-`unknown`) facts.yaml
    # entries and no onchain KPI is seeded in stub_stores, so
    # qa.supply.answer_supply_question falls back to the facts path and
    # always returns "faq" -- not a flaky faq/rag/refusal tri-state.
    assert body["meta"]["answer_kind"] == "faq"

    _assert_renders_nonempty_markdownv2(body)


# ───────────────────────── private chat: free-text question ─────────────────────────


def test_private_free_text_question_round_trips_through_real_adapter_and_core(client):
    text = "what is the total supply of CPX?"
    message = {
        "message_id": 30,
        "from": {"id": 333, "username": "carol", "language_code": "en"},
        "chat": {"id": 333, "type": "private"},
        "date": 1753600000,
        "text": text,
    }

    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)
    assert envelope is not None
    assert envelope["is_dm"] is True
    assert envelope["command"] is None

    resp = client.post("/v1/messages", json=envelope)
    assert resp.status_code == 200
    body = resp.json()
    _assert_well_formed_c2(body)
    assert body["meta"]["answer_kind"] == "faq"

    _assert_renders_nonempty_markdownv2(body)


# ───────────────────────── negative: unaddressed group chatter ─────────────────────────


def test_unaddressed_group_chatter_is_gated_by_adapter_and_never_sent_to_core():
    """C1 rule (telegram_adapter/envelope.py docstring): group text without
    an explicit @mention and without a native command is silently dropped
    by the adapter -- translate_update returns None and the caller must not
    POST anything to /v1/messages for it. This is the adapter's own real
    gate function, not a re-implementation of it in the test."""
    message = {
        "message_id": 40,
        "from": {"id": 444, "username": "dave"},
        "chat": {"id": -1009999, "type": "supergroup"},
        "date": 1753600000,
        "text": "just chatting here, no bot involved",
    }

    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)
    assert envelope is None  # adapter's real gate refuses to forward this -- nothing to POST
