"""C1 envelope translation (adapter -> core).

Pure and network-free: operates on plain dicts shaped exactly like
Telegram's own webhook "Update" JSON (https://core.telegram.org/bots/api
#update), never on python-telegram-bot's `Update` object. That keeps this
module (and its tests) fully independent of any live Telegram connection --
a fixture is just a dict literal shaped like real Telegram JSON.

Mention-gating semantics mirror the live bot's
`core/message_handler.py::BotMessageHandler._should_process_message`
(DO NOT MODIFY that file -- it is the behavioral reference this adapter
must match, not a dependency of this adapter):
  - DMs: always process.
  - Groups, a native command (`/cmd` or `/cmd@BotName`): always process --
    Telegram's own `CommandHandler` routing in the live bot does not gate
    commands on an explicit @mention either, and a `/command` is
    inherently addressed at the bot regardless of mention syntax.
  - Groups, plain text: process only if the bot is explicitly @mentioned
    (entity match, with the same substring fallback the live bot uses for
    entity-detection edge cases); otherwise the update is silently
    dropped -- never forwarded to Century Core at all.
"""
from datetime import datetime, timezone
from typing import Optional


def _iso_utc(unix_ts: int) -> str:
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_command_entity(text: str, entities: list) -> Optional[dict]:
    for entity in entities or []:
        if entity.get("type") == "bot_command" and entity.get("offset") == 0:
            return entity
    return None


def _is_explicit_mention(text: str, entities: list, bot_username: str) -> bool:
    if not bot_username:
        return False
    needle = f"@{bot_username}".lower()
    for entity in entities or []:
        if entity.get("type") == "mention":
            offset, length = entity["offset"], entity["length"]
            mention_text = text[offset : offset + length]
            if mention_text.lower() == needle:
                return True
    # Substring fallback -- mirrors the live bot's tolerance for Telegram
    # entity-detection edge cases (core/message_handler.py).
    return needle in text.lower()


def translate_update(update: dict, *, bot_username: str) -> Optional[dict]:
    """Translate one Telegram webhook update into a C1 envelope dict.

    Returns None when the update should be silently ignored: anything
    that isn't a text message, or unaddressed group chatter (mention
    gating). A None return means "do not call Century Core at all" -- the
    caller must not POST anything to /v1/messages for it.
    """
    message = update.get("message")
    if message is None:
        return None  # edited_message / channel_post / etc. -- out of scope for WP-6a

    text = message.get("text")
    if text is None:
        return None  # non-text message (photo, sticker, ...) -- out of scope

    chat = message.get("chat", {})
    is_dm = chat.get("type") == "private"
    entities = message.get("entities", [])

    command_entity = _find_command_entity(text, entities)
    command = None
    if command_entity is not None:
        length = command_entity["length"]
        raw_command = text[:length]  # e.g. "/price@CenturyBot"
        name = raw_command[1:].split("@", 1)[0].lower()
        args = text[length:].strip()
        command = {"name": name, "args": args}

    if command is not None:
        mentioned = True  # a native command is inherently addressed at the bot
    elif is_dm:
        mentioned = True
    else:
        mentioned = _is_explicit_mention(text, entities, bot_username)

    if not is_dm and not mentioned:
        return None  # unaddressed group chatter -- never forwarded to core

    thread_ref = message.get("message_thread_id")
    from_user = message.get("from") or {}

    return {
        "channel": "telegram",
        "channel_msg_id": str(message["message_id"]),
        "user_ref": str(from_user.get("id", chat.get("id"))),
        "chat_ref": str(chat["id"]),
        "thread_ref": str(thread_ref) if thread_ref is not None else None,
        "text": text,
        "command": command,
        "is_dm": is_dm,
        "mentioned": mentioned,
        "locale": from_user.get("language_code"),
        "ts": _iso_utc(message["date"]),
    }
