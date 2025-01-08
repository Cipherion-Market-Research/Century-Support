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

async def send_message_3(context):
    await send_message(context, "start_message")

def schedule_periodic_messages(application: Application, interval_seconds: int = 48*3600, offset_seconds: int = 24*3600):
    """
    Schedule periodic messages.
    
    :param application: The Telegram Application instance.
    :param interval_seconds: Interval between messages in seconds (default 48 hours).
    :param offset_seconds: Offset for the second message in seconds (default 24 hours).
    """
    # Schedule Message 1 every 48 hours (privacy reminder)
    application.job_queue.run_repeating(
        send_message_1, 
        interval=interval_seconds,
        first=0
    )

    # Schedule Message 2 every 48 hours, offset by 24 hours (admin warning)
    application.job_queue.run_repeating(
        send_message_2, 
        interval=interval_seconds,
        first=offset_seconds
    )

    # Schedule start message every 96 hours
    application.job_queue.run_repeating(
        send_message_3,
        interval=96*3600,  # 96 hours
        first=12*3600  # First message after 12 hours
    )

    logger.info("Scheduled periodic messages successfully")
