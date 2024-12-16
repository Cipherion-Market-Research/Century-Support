# core/scheduler.py

import logging
from telegram.ext import Application
from config.config import Config
from config.constants import SCHEDULED_MESSAGES  # Assuming you moved messages here
from utils.logger import setup_logger

logger = setup_logger(__name__)

async def send_message(context, message_key):
    message = SCHEDULED_MESSAGES.get(message_key, "Hello!")
    try:
        await context.bot.send_message(
            chat_id=Config.TELEGRAM_GROUP_ID, 
            text=message, 
            parse_mode="Markdown"
        )
        logger.info(f"Sent periodic '{message_key}'")
    except Exception as e:
        logger.error(f"Error sending '{message_key}': {e}")

async def send_message_1(context):
    await send_message(context, "privacy_reminder")

async def send_message_2(context):
    await send_message(context, "admin_warning")

def schedule_periodic_messages(application: Application, interval_seconds: int = 24*3600, offset_seconds: int = 3*3600):
    """
    Schedule two periodic messages.
    
    :param application: The Telegram Application instance.
    :param interval_seconds: Interval between messages in seconds.
    :param offset_seconds: Offset for the second message in seconds.
    """
    # Schedule Message 1 every `interval_seconds`, starting immediately
    application.job_queue.run_repeating(
        send_message_1, 
        interval=interval_seconds, 
        first=0
    )

    # Schedule Message 2 every `interval_seconds`, starting after `offset_seconds`
    application.job_queue.run_repeating(
        send_message_2, 
        interval=interval_seconds, 
        first=offset_seconds
    )

    logger.info("Scheduled periodic messages successfully")
