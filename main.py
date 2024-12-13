######## APPROACH ORIGINAL #########

# import asyncio
# from telegram.ext import Application, CommandHandler, MessageHandler, filters
# from config.config import Config
# from core.message_handler import BotMessageHandler
# from utils.logger import setup_logger
# from utils.db_manager import DatabaseManager
# from utils.cache_manager import CacheManager

# logger = setup_logger()

# class Bot:
#     def __init__(self):
#         self.db_manager = DatabaseManager()
#         self.cache_manager = CacheManager()
#         self.message_handler = None
#         self.application = None

#     async def initialize(self):
#         # Initialize cache
#         await self.cache_manager.init()
        
#         # Initialize message handler
#         self.message_handler = BotMessageHandler(self.db_manager, self.cache_manager)
        
#         # Initialize bot
#         self.application = Application.builder().token(Config.TELEGRAM_TOKEN).build()
        
#         # Add handlers
#         self.application.add_handler(CommandHandler("start", self.message_handler.handle_start))
#         self.application.add_handler(CommandHandler("help", self.message_handler.handle_help))
#         self.application.add_handler(
#             MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler.handle_message)
#         )

#     async def run(self):
#         try:
#             await self.initialize()
#             logger.info("Bot started successfully")
#             await self.application.run_polling(drop_pending_updates=True)
#         except Exception as e:
#             logger.error(f"Critical error in main: {e}")
#             raise

#     async def shutdown(self):
#         try:
#             if self.application:
#                 await self.application.shutdown()
#             if self.cache_manager and self.cache_manager.redis:
#                 await self.cache_manager.redis.close()
#         except Exception as e:
#             logger.error(f"Error during shutdown: {e}")

# def validate_environment():
#     required_vars = [
#         'TELEGRAM_TOKEN',
#         'REDIS_URL',
#         'MONGODB_URI',
#         'OPENAI_API_KEY'
#     ]
    
#     missing = [var for var in required_vars if not getattr(Config, var, None)]
#     if missing:
#         raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# def main():
#     bot = Bot()
#     asyncio.run(bot.run())

# if __name__ == "__main__":
#     try:
#         main()
#     except KeyboardInterrupt:
#         logger.info("Bot stopped by user")
#     except Exception as e:
#         logger.critical(f"Fatal error: {e}")
#         raise

######## APPROACH A #########
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


######## APPROACH B #########

# import asyncio
# from telegram.ext import Application, CommandHandler, MessageHandler, filters
# from config.config import Config
# from core.message_handler import BotMessageHandler
# from utils.logger import setup_logger
# from utils.db_manager import DatabaseManager
# from utils.cache_manager import CacheManager

# logger = setup_logger()

# async def main():
#     db_manager = DatabaseManager()
#     cache_manager = CacheManager()
#     await cache_manager.init()

#     message_handler = BotMessageHandler(db_manager, cache_manager)
#     application = Application.builder().token(Config.TELEGRAM_TOKEN).build()

#     application.add_handler(CommandHandler("start", message_handler.handle_start))
#     application.add_handler(CommandHandler("help", message_handler.handle_help))
#     application.add_handler(
#         MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler.handle_message)
#     )

#     logger.info("Bot started successfully")

#     # Manually initialize and start the bot
#     await application.initialize()
#     await application.start()
#     await application.updater.start_polling()
#     # Wait for bot to be stopped with Ctrl+C, etc.
#     await application.idle()
#     # On shutdown:
#     await application.updater.stop()
#     await application.stop()

# if __name__ == "__main__":
#     asyncio.run(main())