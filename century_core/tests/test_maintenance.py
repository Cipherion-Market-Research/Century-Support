"""WP-7c: global maintenance-mode switch, century_core side.

Covers the rollback-ledger hard requirements: flag set -> a valid C2
ResponseIR holding message that still passes response_guard (not bypassed);
flag absent -> normal routing; a Redis error fails open.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from century_core import maintenance
from century_core.deps import get_stores
from century_core.maintenance import MAINTENANCE_KEY, get_maintenance_message
from century_core.routes import messages

from .test_routes import BASE_MESSAGE


@pytest.fixture
def client(stub_stores):
    app = FastAPI()
    app.include_router(messages.router)
    app.dependency_overrides[get_stores] = lambda: stub_stores
    with TestClient(app) as c:
        yield c


# ─────────────────────────── get_maintenance_message ───────────────────────────


@pytest.mark.asyncio
async def test_get_maintenance_message_absent_key_returns_none(fake_redis):
    assert await get_maintenance_message(fake_redis) is None


@pytest.mark.asyncio
async def test_get_maintenance_message_custom_value(fake_redis):
    await fake_redis.set(MAINTENANCE_KEY, "Back online at 3pm UTC.")
    assert await get_maintenance_message(fake_redis) == "Back online at 3pm UTC."


@pytest.mark.asyncio
async def test_get_maintenance_message_empty_value_falls_back_to_default(fake_redis):
    await fake_redis.set(MAINTENANCE_KEY, "")
    message = await get_maintenance_message(fake_redis)
    assert message == maintenance.Config.MAINTENANCE_DEFAULT_MESSAGE


@pytest.mark.asyncio
async def test_get_maintenance_message_fails_open_on_redis_error():
    class ExplodingRedis:
        async def get(self, key):
            raise ConnectionError("redis unreachable")

    assert await get_maintenance_message(ExplodingRedis()) is None


# ────────────────────────────── /v1/messages route ──────────────────────────────


def test_maintenance_message_served_and_passes_guard(client, stub_stores):
    stub_stores.kpi.redis._data[MAINTENANCE_KEY] = "Scheduled maintenance in progress."
    resp = client.post(
        "/v1/messages",
        json={**BASE_MESSAGE, "text": "/price", "command": {"name": "price", "args": ""}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["answer_kind"] == "refusal"
    assert len(body["blocks"]) == 1
    assert body["blocks"][0]["type"] == "paragraph"
    assert body["blocks"][0]["md"] == "Scheduled maintenance in progress."


def test_maintenance_mode_skips_command_dispatch_entirely(client, stub_stores):
    stub_stores.kpi.redis._data[MAINTENANCE_KEY] = "Down for maintenance."
    resp = client.post(
        "/v1/messages",
        json={**BASE_MESSAGE, "text": "/price", "command": {"name": "price", "args": ""}},
    )
    body = resp.json()
    # Normal /price dispatch would answer with a "fact" block labelled "CPX
    # Price" (see test_routes.py) -- proves the command path never ran.
    assert body["meta"]["answer_kind"] != "command"


def test_maintenance_mode_empty_value_uses_default_message(client, stub_stores):
    stub_stores.kpi.redis._data[MAINTENANCE_KEY] = ""
    resp = client.post("/v1/messages", json={**BASE_MESSAGE, "text": "hi", "command": None})
    body = resp.json()
    assert body["blocks"][0]["md"] == maintenance.Config.MAINTENANCE_DEFAULT_MESSAGE


def test_no_maintenance_key_routes_normally(client):
    resp = client.post(
        "/v1/messages",
        json={**BASE_MESSAGE, "text": "/price", "command": {"name": "price", "args": ""}},
    )
    body = resp.json()
    assert body["meta"]["answer_kind"] == "command"


def test_maintenance_check_redis_error_fails_open_to_normal_routing(client, stub_stores, monkeypatch):
    async def _raise(self, key):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(type(stub_stores.kpi.redis), "get", _raise, raising=False)
    resp = client.post(
        "/v1/messages",
        json={**BASE_MESSAGE, "text": "/price", "command": {"name": "price", "args": ""}},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["answer_kind"] == "command"
