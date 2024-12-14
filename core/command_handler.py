from telegram import Update
from telegram.ext import ContextTypes
from config.constants import BOT_RESPONSES
from utils.logger import setup_logger

logger = setup_logger()


class BotCommandHandler:
    def __init__(self, db_manager, cache_manager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager

    async def handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle bot commands"""
        try:
            command = update.message.text.split()[0][1:]  # Remove the '/'
            user_id = update.effective_user.id

            command_handlers = {
                "start": self._handle_start,
                "help": self._handle_help,
                "price": self._handle_price,
                "whitepaper": self._handle_whitepaper,
                "contract": self._handle_contract,
                "stats": self._handle_stats,
                "certik": self._handle_certik,
            }

            if command in command_handlers:
                await command_handlers[command](update, context)
            else:
                await update.message.reply_text(
                    "Unknown command. Use /help to see available commands."
                )

        except Exception as e:
            logger.error(f"Error handling command: {e}")
            await update.message.reply_text(BOT_RESPONSES["error"], parse_mode="Markdown")

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["welcome"], parse_mode="Markdown")

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["help"], parse_mode="Markdown")

    async def _handle_contract(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["contract_info"], parse_mode="Markdown")

    async def _handle_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["price_info"], parse_mode="Markdown")

    async def _handle_whitepaper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # If you have logic to fetch a specific section from the whitepaper:
        # user may input a section name after the command.
        # For now, just provide the link:
        await update.message.reply_text(BOT_RESPONSES["whitepaper_info"], parse_mode="Markdown")

    async def _handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["stats_info"], parse_mode="Markdown")

    async def _handle_certik(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["certik_info"], parse_mode="Markdown")
