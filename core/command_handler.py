import json
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
        try:
            raw_command = update.message.text.split()[0]  # e.g. "/certik@CiphexHelpBot"
            command = raw_command.split('@')[0][1:]       # Removes '/', then splits at '@' to handle bot mentions
            user_id = update.effective_user.id

            command_handlers = {
                "start": self._handle_start,
                "help": self._handle_help,
                "price": self._handle_price,
                "whitepaper": self._handle_whitepaper,
                "ca": self._handle_contract,
                "stats": self._handle_stats,
                "audit": self._handle_certik,
                "presale": self._handle_presale,
                "website": self._handle_website,
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
        await update.message.reply_text(BOT_RESPONSES["whitepaper_info"], parse_mode="Markdown")

    async def _handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stats_data_str = await self.cache_manager.redis.get("ciphex_stats")
        if stats_data_str:
            stats_data = json.loads(stats_data_str)
            # Directly access the keys, which are strings
            cipherions = stats_data.get('cipherions', 'Unknown')
            total_contributions = stats_data.get('totalContributions', 'Unknown')
            total_cpx_presold = stats_data.get('totalCPXPresold', 'Unknown')
            total_staked = stats_data.get('totalStaked', 'Unknown')
            percent_staked = stats_data.get('percentStaked', 'Unknown')

            formatted_stats = (
                f"**Community & Presale Stats**:\n"
                f"- Total Community Members: {cipherions}\n"
                f"- Total Funds Raised: {total_contributions}\n"
                f"- Total CPX Purchased: {total_cpx_presold} tokens\n"
                f"- Total Staked: {total_staked} tokens\n"
                f"- Percent Staked: {percent_staked}%\n"
            )
            await update.message.reply_text(formatted_stats, parse_mode="Markdown")
        else:
            await update.message.reply_text(BOT_RESPONSES["stats_info"], parse_mode="Markdown")

    async def _handle_certik(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["certik_info"], parse_mode="Markdown")

    async def _handle_presale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["presale_info"], parse_mode="Markdown")

    async def _handle_website(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["website_info"], parse_mode="Markdown")
