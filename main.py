import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config.config import Config
from core.message_handler import BotMessageHandler
from utils.logger import setup_logger
from utils.db_manager import DatabaseManager
from utils.cache_manager import CacheManager

logger = setup_logger()

async def post_init(application: Application):
    # Run async initialization tasks here
    # This code is guaranteed to be called within PTB's event loop
    await application.bot_data["cache_manager"].init()
    logger.info("Cache initialization completed in post_init.")

if __name__ == "__main__":
    # Initialize managers (without async methods)
    db_manager = DatabaseManager()
    cache_manager = CacheManager()

    # Prepare the message handler
    message_handler = BotMessageHandler(db_manager, cache_manager)

    # Pass managers via bot_data or application.user_data if needed
    application = (
        Application.builder()
        .token(Config.TELEGRAM_TOKEN)
        .post_init(post_init)  # Register the post_init callback
        .build()
    )
    # Store references in application’s data for post_init usage
    application.bot_data["db_manager"] = db_manager
    application.bot_data["cache_manager"] = cache_manager

    # Add handlers
    application.add_handler(CommandHandler("start", message_handler.handle_start))
    application.add_handler(CommandHandler("help", message_handler.handle_help))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler.handle_message))

    logger.info("Bot started successfully")
    application.run_polling(drop_pending_updates=True)