"""Sends rendered messages via python-telegram-bot's `Bot`.

Isolated in its own module (rather than folded into webhook.py) so
markdown.py and envelope.py stay importable, and fully testable, without
python-telegram-bot in the loop at all -- only this module and webhook.py
touch the `telegram` package.
"""
from typing import List, Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from telegram_adapter.markdown import RenderedMessage


def _keyboard(buttons: List[tuple]) -> Optional[InlineKeyboardMarkup]:
    if not buttons:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, url=url)] for label, url in buttons])


async def send_rendered_messages(
    bot: Bot,
    *,
    chat_id: int,
    thread_id: Optional[int],
    messages: List[RenderedMessage],
) -> None:
    for msg in messages:
        await bot.send_message(
            chat_id=chat_id,
            text=msg.text,
            parse_mode="MarkdownV2",
            reply_markup=_keyboard(msg.buttons),
            message_thread_id=thread_id,
        )


async def send_plain_text(
    bot: Bot,
    *,
    chat_id: int,
    thread_id: Optional[int],
    text: str,
) -> None:
    """Used only for CORE_FAILURE_MESSAGE -- plain text, no MarkdownV2
    parsing, so a static string with no special characters can never fail
    to send because of formatting."""
    await bot.send_message(chat_id=chat_id, text=text, message_thread_id=thread_id)
