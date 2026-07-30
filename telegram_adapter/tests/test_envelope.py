"""C1 envelope translation tests.

Fixtures are plain dicts shaped exactly like Telegram's webhook "Update"
JSON -- no live network, no python-telegram-bot objects.
"""
from telegram_adapter.envelope import translate_update

BOT_USERNAME = "CenturyBot"


def _mention_entity(text: str) -> dict:
    needle = f"@{BOT_USERNAME}"
    offset = text.index(needle)
    return {"type": "mention", "offset": offset, "length": len(needle)}


def _command_entity(text: str) -> dict:
    # Telegram's bot_command entity covers "/name" or "/name@BotName" from
    # offset 0 up to (but not including) any trailing space/args.
    command_token = text.split(" ", 1)[0]
    return {"type": "bot_command", "offset": 0, "length": len(command_token)}


def _update(message: dict) -> dict:
    return {"update_id": 1, "message": message}


# ────────────────────────────────────── DM ──────────────────────────────────────


def test_dm_always_processed_and_mentioned_true():
    message = {
        "message_id": 10,
        "from": {"id": 111, "username": "alice", "language_code": "en"},
        "chat": {"id": 111, "type": "private"},
        "date": 1753600000,
        "text": "what is the price?",
    }
    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)

    assert envelope is not None
    assert envelope["channel"] == "telegram"
    assert envelope["channel_msg_id"] == "10"
    assert envelope["user_ref"] == "111"
    assert envelope["chat_ref"] == "111"
    assert envelope["thread_ref"] is None
    assert envelope["text"] == "what is the price?"
    assert envelope["command"] is None
    assert envelope["is_dm"] is True
    assert envelope["mentioned"] is True
    assert envelope["locale"] == "en"
    assert envelope["ts"] == "2025-07-27T07:06:40Z"


# ─────────────────────────────────── Group, mentioned ───────────────────────────────────


def test_group_message_with_explicit_mention_is_processed():
    text = f"@{BOT_USERNAME} what is the price?"
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
    assert envelope["chat_ref"] == "-1001234"
    assert envelope["text"] == text  # C1 rule: mention text left in place


def test_group_message_mention_substring_fallback_without_entity():
    # Mirrors the live bot's tolerance for missed entity detection
    # (core/message_handler.py's substring fallback) -- no `entities` list
    # at all, but the @mention text is present.
    text = f"hey @{BOT_USERNAME} what is the price?"
    message = {
        "message_id": 21,
        "from": {"id": 225},
        "chat": {"id": -1001234, "type": "group"},
        "date": 1753600000,
        "text": text,
    }
    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)

    assert envelope is not None
    assert envelope["mentioned"] is True


# ─────────────────────────── Group, NOT mentioned -- ignored ───────────────────────────


def test_group_message_without_mention_is_ignored():
    message = {
        "message_id": 22,
        "from": {"id": 223, "username": "carol"},
        "chat": {"id": -1001234, "type": "supergroup"},
        "date": 1753600000,
        "text": "just chatting here, no bot involved",
    }
    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)

    assert envelope is None  # never forwarded to Century Core


def test_group_message_mentioning_a_different_bot_is_ignored():
    message = {
        "message_id": 23,
        "from": {"id": 226},
        "chat": {"id": -1001234, "type": "supergroup"},
        "date": 1753600000,
        "text": "@SomeOtherBot help me",
        "entities": [{"type": "mention", "offset": 0, "length": len("@SomeOtherBot")}],
    }
    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)

    assert envelope is None


# ────────────────────────────────── Native command ──────────────────────────────────


def test_native_command_in_dm_populates_command_field():
    text = "/price"
    message = {
        "message_id": 30,
        "from": {"id": 111},
        "chat": {"id": 111, "type": "private"},
        "date": 1753600000,
        "text": text,
        "entities": [_command_entity(text)],
    }
    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)

    assert envelope is not None
    assert envelope["command"] == {"name": "price", "args": ""}
    assert envelope["mentioned"] is True


def test_native_command_in_group_processed_without_explicit_mention():
    # Matches the live bot's CommandHandler behavior: a native /command is
    # always processed in a group, with no separate @mention required.
    text = f"/price@{BOT_USERNAME} btc"
    message = {
        "message_id": 31,
        "from": {"id": 227},
        "chat": {"id": -1009999, "type": "group"},
        "date": 1753600000,
        "text": text,
        "entities": [_command_entity(text)],
    }
    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)

    assert envelope is not None
    assert envelope["is_dm"] is False
    assert envelope["mentioned"] is True
    # Bot-mention suffix is stripped from the command name...
    assert envelope["command"] == {"name": "price", "args": "btc"}
    # ...but left in place in the raw text field (C1 rule).
    assert envelope["text"] == text


def test_unknown_command_still_populates_command_field():
    # C1 rule: adapters don't validate against the registry -- core does.
    text = "/nonexistent"
    message = {
        "message_id": 32,
        "from": {"id": 228},
        "chat": {"id": 228, "type": "private"},
        "date": 1753600000,
        "text": text,
        "entities": [_command_entity(text)],
    }
    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)

    assert envelope["command"] == {"name": "nonexistent", "args": ""}


# ───────────────────────────────────── Thread ─────────────────────────────────────


def test_message_thread_id_becomes_thread_ref():
    text = f"@{BOT_USERNAME} question in a topic"
    message = {
        "message_id": 40,
        "from": {"id": 229},
        "chat": {"id": -1005555, "type": "supergroup"},
        "message_thread_id": 777,
        "date": 1753600000,
        "text": text,
        "entities": [_mention_entity(text)],
    }
    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)

    assert envelope is not None
    assert envelope["thread_ref"] == "777"


def test_no_thread_id_gives_none_thread_ref():
    message = {
        "message_id": 41,
        "from": {"id": 111},
        "chat": {"id": 111, "type": "private"},
        "date": 1753600000,
        "text": "hi",
    }
    envelope = translate_update(_update(message), bot_username=BOT_USERNAME)

    assert envelope["thread_ref"] is None


# ───────────────────────────────── Non-text updates ─────────────────────────────────


def test_non_message_update_is_ignored():
    update = {"update_id": 2, "edited_message": {"message_id": 1, "text": "edited"}}
    assert translate_update(update, bot_username=BOT_USERNAME) is None


def test_non_text_message_is_ignored():
    message = {
        "message_id": 50,
        "from": {"id": 111},
        "chat": {"id": 111, "type": "private"},
        "date": 1753600000,
        "sticker": {"file_id": "abc"},
    }
    assert translate_update(_update(message), bot_username=BOT_USERNAME) is None
