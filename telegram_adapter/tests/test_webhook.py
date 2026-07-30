"""Webhook endpoint tests: secret-token rejection, mention-gating never
reaching Century Core, core-failure static fallback, successful render+send
(incl. buttons), and the top-level error funnel (unhandled exception still
returns 200 so Telegram doesn't retry-storm). A fake duck-typed Bot stands
in for python-telegram-bot's real Bot -- no real Telegram connection is
ever made.
"""
import pytest
from aiohttp.test_utils import TestClient, TestServer

import telegram_adapter.webhook as webhook_module
from telegram_adapter.config import Config
from telegram_adapter.core_client import CORE_FAILURE_MESSAGE
from telegram_adapter.webhook import create_webhook_app


class FakeBot:
    def __init__(self, username="CenturyBot"):
        self.username = username
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


DM_COMMAND_UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 1,
        "from": {"id": 111, "language_code": "en"},
        "chat": {"id": 111, "type": "private"},
        "date": 1753600000,
        "text": "/price",
        "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
    },
}

GROUP_NON_MENTION_UPDATE = {
    "update_id": 2,
    "message": {
        "message_id": 2,
        "from": {"id": 222},
        "chat": {"id": -100999, "type": "supergroup"},
        "date": 1753600000,
        "text": "just chatting, no bot involved",
    },
}


@pytest.fixture
def bot():
    return FakeBot()


async def _client(bot_obj) -> TestClient:
    app = create_webhook_app(bot=bot_obj, session=object())
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(Config, "TELEGRAM_WEBHOOK_SECRET", "s3cr3t")


# ────────────────────────────────── /health ──────────────────────────────────


async def test_health_endpoint_ok(bot):
    client = await _client(bot)
    try:
        resp = await client.get("/health")
        assert resp.status == 200
        assert (await resp.json())["ok"] is True
    finally:
        await client.close()


# ──────────────────────────── Webhook secret validation ────────────────────────────


async def test_webhook_rejects_missing_secret_header(bot):
    client = await _client(bot)
    try:
        resp = await client.post(Config.WEBHOOK_PATH, json=DM_COMMAND_UPDATE)
        assert resp.status == 401
        assert bot.sent == []
    finally:
        await client.close()


async def test_webhook_rejects_wrong_secret_header(bot):
    client = await _client(bot)
    try:
        resp = await client.post(
            Config.WEBHOOK_PATH,
            json=DM_COMMAND_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert resp.status == 401
        assert bot.sent == []
    finally:
        await client.close()


async def test_webhook_rejects_when_no_secret_configured(bot, monkeypatch):
    # Closed-by-default: an unset TELEGRAM_WEBHOOK_SECRET must never mean
    # "accept everything".
    monkeypatch.setattr(Config, "TELEGRAM_WEBHOOK_SECRET", "")
    client = await _client(bot)
    try:
        resp = await client.post(
            Config.WEBHOOK_PATH,
            json=DM_COMMAND_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": ""},
        )
        assert resp.status == 401
    finally:
        await client.close()


async def test_webhook_accepts_correct_secret(bot, monkeypatch):
    async def fake_post_message(session, envelope):
        return {"blocks": [{"type": "heading", "text": "CPX Price"}], "meta": {"answer_kind": "command"}}

    monkeypatch.setattr(webhook_module, "post_message", fake_post_message)
    client = await _client(bot)
    try:
        resp = await client.post(
            Config.WEBHOOK_PATH,
            json=DM_COMMAND_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )
        assert resp.status == 200
        assert len(bot.sent) == 1
        assert bot.sent[0]["chat_id"] == 111
        assert bot.sent[0]["text"] == "*CPX Price*"
        assert bot.sent[0]["parse_mode"] == "MarkdownV2"
    finally:
        await client.close()


# ────────────────────────────── Mention-gating passthrough ──────────────────────────────


async def test_webhook_never_calls_core_for_ignored_group_message(bot, monkeypatch):
    called = {"n": 0}

    async def fake_post_message(session, envelope):
        called["n"] += 1
        return None

    monkeypatch.setattr(webhook_module, "post_message", fake_post_message)
    client = await _client(bot)
    try:
        resp = await client.post(
            Config.WEBHOOK_PATH,
            json=GROUP_NON_MENTION_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )
        assert resp.status == 200
        assert called["n"] == 0
        assert bot.sent == []
    finally:
        await client.close()


# ───────────────────────────────── Core-failure fallback ─────────────────────────────────


async def test_webhook_core_failure_sends_static_fallback_message(bot, monkeypatch):
    async def fake_post_message_fails(session, envelope):
        return None

    monkeypatch.setattr(webhook_module, "post_message", fake_post_message_fails)
    client = await _client(bot)
    try:
        resp = await client.post(
            Config.WEBHOOK_PATH,
            json=DM_COMMAND_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )
        assert resp.status == 200
        assert len(bot.sent) == 1
        assert bot.sent[0]["text"] == CORE_FAILURE_MESSAGE
        assert "parse_mode" not in bot.sent[0]  # plain text, no MarkdownV2 parsing risk
    finally:
        await client.close()


# ─────────────────────────── Buttons attach to the outgoing message ───────────────────────────


async def test_webhook_buttons_block_becomes_reply_markup(bot, monkeypatch):
    async def fake_post_message(session, envelope):
        return {
            "blocks": [
                {"type": "heading", "text": "Claim"},
                {"type": "buttons", "items": [{"label": "Open portal", "url": "https://claim.ciphex.io"}]},
            ],
            "meta": {"answer_kind": "command"},
        }

    monkeypatch.setattr(webhook_module, "post_message", fake_post_message)
    client = await _client(bot)
    try:
        resp = await client.post(
            Config.WEBHOOK_PATH,
            json=DM_COMMAND_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )
        assert resp.status == 200
        assert len(bot.sent) == 1
        markup = bot.sent[0]["reply_markup"]
        assert markup is not None
        assert markup.inline_keyboard[0][0].text == "Open portal"
        assert markup.inline_keyboard[0][0].url == "https://claim.ciphex.io"
    finally:
        await client.close()


# ───────────────────────────────── Error funnel ─────────────────────────────────


async def test_webhook_unhandled_exception_still_returns_200_and_does_not_crash(bot, monkeypatch):
    # The live bot has no top-level error handler (core/message_handler.py,
    # core/command_handler.py); this adapter's hard requirement is the
    # opposite -- an unhandled exception anywhere in the pipeline must be
    # caught, logged, and answered with a fast 200 rather than propagating
    # or leaving Telegram to retry-storm the same update.
    async def fake_post_message_raises(session, envelope):
        raise RuntimeError("boom")

    monkeypatch.setattr(webhook_module, "post_message", fake_post_message_raises)
    client = await _client(bot)
    try:
        resp = await client.post(
            Config.WEBHOOK_PATH,
            json=DM_COMMAND_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
        )
        assert resp.status == 200
    finally:
        await client.close()


async def test_webhook_invalid_json_body_returns_400(bot):
    client = await _client(bot)
    try:
        resp = await client.post(
            Config.WEBHOOK_PATH,
            data=b"not json",
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t", "Content-Type": "application/json"},
        )
        assert resp.status == 400
    finally:
        await client.close()
