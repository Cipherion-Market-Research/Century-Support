import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config.config import Config
from core.data_syncer import DataSyncer
from core.message_handler import BotMessageHandler
from core.command_handler import BotCommandHandler
from utils.logger import setup_logger
from utils.db_manager import DatabaseManager
from utils.cache_manager import CacheManager

logger = setup_logger()

async def post_init(application: Application):
    await application.bot_data["cache_manager"].init()
    logger.info("Cache initialization completed in post_init.")
    
    # Initialize DataSyncer
    db_manager = application.bot_data["db_manager"]
    cache_manager = application.bot_data["cache_manager"]
    data_syncer = DataSyncer(db_manager, cache_manager)

    # Run sync_all once at startup
    await data_syncer.sync_all()
    logger.info("Initial data sync completed.")

if __name__ == "__main__":
    db_manager = DatabaseManager()
    cache_manager = CacheManager()

    # Prepare handlers
    # message_handler handles non-command queries (fallback to AI)
    message_handler = BotMessageHandler(db_manager, cache_manager)
    # command_handler handles all commands
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
    application.add_handler(CommandHandler("contract", command_handler.handle_command))
    application.add_handler(CommandHandler("stats", command_handler.handle_command))
    application.add_handler(CommandHandler("certik", command_handler.handle_command))

    # Message handler for non-command messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler.handle_message))

    logger.info("Bot started successfully")
    application.run_polling(drop_pending_updates=True)
