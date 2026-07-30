"""Century Core HTTP client tests: success, retry-then-succeed, exhausted
retries -> None (caller falls back to CORE_FAILURE_MESSAGE), and timeout
handling. Uses a local in-process aiohttp stub server bound to loopback
(aiohttp.test_utils) -- no real network, no live Telegram, no real Century
Core.
"""
import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from telegram_adapter.config import Config
from telegram_adapter.core_client import post_message

ENVELOPE = {
    "channel": "telegram",
    "channel_msg_id": "1",
    "user_ref": "111",
    "chat_ref": "111",
    "thread_ref": None,
    "text": "/price",
    "command": {"name": "price", "args": ""},
    "is_dm": True,
    "mentioned": True,
    "locale": None,
    "ts": "2026-07-20T00:00:00Z",
}


async def _stub_client(handler) -> TestClient:
    app = web.Application()
    app.router.add_post("/v1/messages", handler)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    # Keep the suite fast: real production defaults would make a
    # retry-exhaustion test take seconds.
    monkeypatch.setattr(Config, "CORE_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(Config, "CORE_RETRY_BASE_DELAY_S", 0.01)
    monkeypatch.setattr(Config, "CORE_HTTP_TIMEOUT_S", 0.2)


async def test_post_message_returns_response_ir_on_200(monkeypatch):
    async def handler(request):
        body = await request.json()
        assert body == ENVELOPE
        return web.json_response({"blocks": [], "meta": {"answer_kind": "command"}})

    client = await _stub_client(handler)
    try:
        monkeypatch.setattr(Config, "CENTURY_CORE_URL", str(client.make_url("")))
        result = await post_message(client.session, ENVELOPE)
        assert result == {"blocks": [], "meta": {"answer_kind": "command"}}
    finally:
        await client.close()


async def test_post_message_retries_after_500_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    async def handler(request):
        attempts["n"] += 1
        if attempts["n"] < 2:
            return web.json_response({"error": "boom"}, status=500)
        return web.json_response({"blocks": [], "meta": {"answer_kind": "faq"}})

    client = await _stub_client(handler)
    try:
        monkeypatch.setattr(Config, "CENTURY_CORE_URL", str(client.make_url("")))
        result = await post_message(client.session, ENVELOPE)
        assert result == {"blocks": [], "meta": {"answer_kind": "faq"}}
        assert attempts["n"] == 2
    finally:
        await client.close()


async def test_post_message_returns_none_after_exhausting_retries(monkeypatch):
    attempts = {"n": 0}

    async def handler(request):
        attempts["n"] += 1
        return web.json_response({"error": "down"}, status=500)

    client = await _stub_client(handler)
    try:
        monkeypatch.setattr(Config, "CENTURY_CORE_URL", str(client.make_url("")))
        result = await post_message(client.session, ENVELOPE)
        assert result is None
        assert attempts["n"] == Config.CORE_RETRY_MAX_ATTEMPTS
    finally:
        await client.close()


async def test_post_message_times_out_and_returns_none(monkeypatch):
    async def handler(request):
        await asyncio.sleep(1.0)  # always exceeds the 0.2s test timeout
        return web.json_response({"blocks": []})

    client = await _stub_client(handler)
    try:
        monkeypatch.setattr(Config, "CENTURY_CORE_URL", str(client.make_url("")))
        result = await post_message(client.session, ENVELOPE)
        assert result is None
    finally:
        await client.close()


async def test_post_message_url_is_exactly_v1_messages(monkeypatch):
    seen_paths = []

    async def handler(request):
        seen_paths.append(request.path)
        return web.json_response({"blocks": [], "meta": {"answer_kind": "command"}})

    client = await _stub_client(handler)
    try:
        monkeypatch.setattr(Config, "CENTURY_CORE_URL", str(client.make_url("")).rstrip("/"))
        await post_message(client.session, ENVELOPE)
        assert seen_paths == ["/v1/messages"]
    finally:
        await client.close()
