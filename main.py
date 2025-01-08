# main.py
import os
import sys
from asyncio import Lock

# Ensure the console uses UTF-8 encoding
if os.name == 'nt':
    os.system('chcp 65001 >nul')  # Windows-specific command to set code page to UTF-8

# Reconfigure stdout and stderr to use UTF-8
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import asyncio
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config.config import Config
from core.data_syncer import DataSyncer
from core.message_handler import BotMessageHandler
from core.command_handler import BotCommandHandler
from core.scheduler import schedule_periodic_messages
from utils.logger import setup_logger
from utils.db_manager import DatabaseManager
from utils.cache_manager import CacheManager

logger = setup_logger()

class Bot:
    def __init__(self):
        self.update_lock = Lock()
        
    async def start(self):
        async with self.update_lock:
            try:
                # Initialize bot
                application = Application.builder().token(Config.BOT_TOKEN).build()
                
                # Add handlers
                application.add_handler(...)
                
                # Start bot
                await application.run_polling()
                
            except Exception as e:
                logger.error(f"Error starting bot: {e}")

async def post_init(application: Application):
    await application.bot_data["cache_manager"].init()
    logger.info("Cache initialization completed in post_init.")

    # Load FAQ data from faq.json
    try:
        with open("data/training/faq.json", "r", encoding="utf-8") as f:
            faq_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load faq.json: {e}")
        faq_data = {}

    faq_dict = {}

    if isinstance(faq_data, dict):
        for category, qa_list in faq_data.items():
            if isinstance(qa_list, list):
                for item in qa_list:
                    if isinstance(item, dict):
                        q = item.get("question", "").strip().lower()
                        a = item.get("answer", "").strip()
                        if q and a:
                            faq_dict[q] = a
                        else:
                            logger.warning(f"Incomplete Q&A pair in faq.json: {item}")
                    else:
                        logger.warning(f"Unexpected item type in faq.json list under category '{category}': {item}")
            else:
                logger.warning(f"Unexpected format for category '{category}' in faq.json. Expected a list.")
    else:
        logger.error("faq.json has an unexpected structure. It should be a dictionary with categories as keys.")

        if faq_dict:
            try:
                await application.bot_data["cache_manager"].redis.set("faq_data", json.dumps(faq_dict))
                logger.info("FAQ data loaded into Redis.")
            except Exception as e:
                logger.error(f"Failed to set faq_data in Redis: {e}")
        else:
            logger.warning("No valid FAQ data found to load into Redis.")

    # Run data sync for whitepaper and other data
    try:
        db_manager = application.bot_data["db_manager"]
        cache_manager = application.bot_data["cache_manager"]
        data_syncer = DataSyncer(db_manager, cache_manager)
        await data_syncer.sync_all()
        logger.info("Initial data sync completed.")
    except Exception as e:
        logger.error(f"Failed to run initial data sync: {e}")

			# Schedule periodic messages
    try:
        # For production, set interval_seconds to 24*3600 (24 hours) and offset_seconds as needed
        schedule_periodic_messages(application, interval_seconds=24*3600, offset_seconds=12*3600)
        logger.info("Scheduled periodic messages successfully.")
    except Exception as e:
        logger.error(f"Failed to schedule periodic messages: {e}")

if __name__ == "__main__":
    db_manager = DatabaseManager()
    cache_manager = CacheManager()

    # Prepare handlers
    message_handler = BotMessageHandler(db_manager, cache_manager)
    command_handler = BotCommandHandler(db_manager, cache_manager)

    application = (
        Application.builder()
        .token(Config.TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.bot_data["db_manager"] = db_manager
    application.bot_data["cache_manager"] = cache_manager

    # Command handlers
    application.add_handler(CommandHandler("start", command_handler.handle_command))
    application.add_handler(CommandHandler("help", command_handler.handle_command))
    application.add_handler(CommandHandler("price", command_handler.handle_command))
    application.add_handler(CommandHandler("whitepaper", command_handler.handle_command))
    application.add_handler(CommandHandler("ca", command_handler.handle_command))
    application.add_handler(CommandHandler("stats", command_handler.handle_command))
    application.add_handler(CommandHandler("audit", command_handler.handle_command))
    application.add_handler(CommandHandler("presale", command_handler.handle_command))
    application.add_handler(CommandHandler("website", command_handler.handle_command))


    # Message handler for non-command messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler.handle_message))

    # Debug handler to log all updates (add after all other handlers)
    async def debug_log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.debug(f"DEBUG LOG ALL UPDATES: {update}")
        if update.message:
            logger.debug(f"Message text: {update.message.text}")
            logger.debug(f"Entities: {update.message.entities}")

    application.add_handler(MessageHandler(filters.ALL, debug_log_all_updates))

    logger.info("Bot started successfully")
    application.run_polling(drop_pending_updates=True)
