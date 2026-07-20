"""HTTP-level integration tests via FastAPI's TestClient, with get_stores
overridden to a stub Stores -- no real Redis/Postgres/OpenAI. Covers C1
command-detection-from-raw-text (adapters don't parse commands themselves
per C1), /v1/facts/:key known+unknown, /v1/broadcasts accept+reject,
/health.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from century_core.deps import get_stores
from century_core.routes import broadcasts, facts, health, messages

BASE_MESSAGE = {
    "channel": "telegram",
    "channel_msg_id": "1",
    "user_ref": "u1",
    "chat_ref": "c1",
    "thread_ref": None,
    "is_dm": True,
    "mentioned": True,
    "locale": None,
    "ts": "2026-07-20T00:00:00Z",
}


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


# ─────────────────────────────── /v1/messages ───────────────────────────────


def test_native_command_field_dispatches(client):
    resp = client.post(
        "/v1/messages",
        json={**BASE_MESSAGE, "text": "/price", "command": {"name": "price", "args": ""}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["answer_kind"] == "command"
    assert body["blocks"][0]["text"] == "CPX Price"


def test_command_detected_from_raw_text_when_command_field_absent(client):
    # C1: "command is non-null only when the platform natively parsed a
    # command... core also detects command-like text itself."
    resp = client.post("/v1/messages", json={**BASE_MESSAGE, "text": "/ca", "command": None})
    assert resp.status_code == 200
    assert resp.json()["meta"]["answer_kind"] == "command"
    assert resp.json()["blocks"][0]["text"] == "CPX Contract Addresses"


def test_command_with_bot_mention_suffix_is_detected(client):
    resp = client.post("/v1/messages", json={**BASE_MESSAGE, "text": "/price@CenturyBot", "command": None})
    assert resp.status_code == 200
    assert resp.json()["meta"]["answer_kind"] == "command"


def test_unrecognized_command_falls_back_to_help(client):
    resp = client.post("/v1/messages", json={**BASE_MESSAGE, "text": "/nonexistent", "command": None})
    assert resp.status_code == 200
    assert "Century" in resp.json()["blocks"][0]["text"]


def test_empty_text_refuses(client):
    resp = client.post("/v1/messages", json={**BASE_MESSAGE, "text": "   ", "command": None})
    assert resp.status_code == 200
    assert resp.json()["meta"]["answer_kind"] == "refusal"


def test_plain_text_question_routes_to_qa(client):
    resp = client.post(
        "/v1/messages", json={**BASE_MESSAGE, "text": "what is the total supply of CPX?", "command": None}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["answer_kind"] in ("faq", "rag", "refusal")


def test_rejects_malformed_c1_envelope(client):
    resp = client.post("/v1/messages", json={"channel": "telegram", "text": "hi"})  # missing required fields
    assert resp.status_code == 422


# ─────────────────────────────── /v1/facts/:key ───────────────────────────────


def test_known_fact_returns_200(client):
    resp = client.get("/v1/facts/tokenomics.max_supply_cpx")
    assert resp.status_code == 200
    body = resp.json()
    assert body["known"] is True
    assert body["value"] == 1500000000
    assert body["source_url"]
    assert body["verified_on"]


def test_missing_fact_returns_404_with_official_link(client):
    resp = client.get("/v1/facts/tokenomics.nonexistent_key")
    assert resp.status_code == 404
    body = resp.json()
    assert body["known"] is False
    assert "ciphex.io" in body["official_link"]


def test_unknown_sentinel_fact_returns_404():
    # round-terms.new_round_lockup_interest is a real fact.yaml key whose
    # value is the `unknown` sentinel (C4) -- must 404 the same as an
    # absent key, not 200 with value: "unknown".
    from facts_store import default_store

    store = default_store()
    fact = store.get("round-terms.new_round_lockup_interest")
    assert fact is not None and fact.is_unknown  # sanity check the fixture assumption


def test_unknown_sentinel_fact_returns_404_via_http(client):
    resp = client.get("/v1/facts/round-terms.new_round_lockup_interest")
    assert resp.status_code == 404


# ─────────────────────────────── /v1/broadcasts ───────────────────────────────


def test_valid_broadcast_is_accepted_and_enqueued(client, stub_stores):
    resp = client.post(
        "/v1/broadcasts",
        json={"blocks": [{"type": "heading", "text": "Ecosystem Update"}], "target": {}},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["enqueued"] is True
    assert body["broadcast_id"]

    queued = stub_stores.kpi.redis._lists["century:broadcasts"]
    assert len(queued) == 1
    envelope = json.loads(queued[0])
    assert envelope["blocks"][0]["text"] == "Ecosystem Update"


def test_broadcast_with_solicitation_language_is_rejected(client):
    resp = client.post(
        "/v1/broadcasts",
        json={"blocks": [{"type": "paragraph", "md": "Buy CPX now, guaranteed returns!"}], "target": {}},
    )
    assert resp.status_code == 422


# ────────────────────────────────── /health ──────────────────────────────────


def test_health_ok_when_stores_reachable(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["checks"]["facts_loaded"] is True
