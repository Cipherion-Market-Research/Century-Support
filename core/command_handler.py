import json
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.constants import BOT_RESPONSES
from config.asset_paths import WELCOME_GIF
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
            # user_id is not used currently but might be needed for future user-specific features
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
        try:
            # Create inline keyboard
            keyboard = [
                [
                    InlineKeyboardButton("Website", url="https://ciphex.io"),
                    InlineKeyboardButton("Whitepaper", url="https://ciphex.io/whitepapers")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send welcome GIF with caption
            with open(WELCOME_GIF, 'rb') as gif:
                await context.bot.send_animation(
                    chat_id=update.effective_chat.id,
                    animation=gif,
                    caption=BOT_RESPONSES["welcome"],
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Error in _handle_start: {e}", exc_info=True)
            await update.message.reply_text(BOT_RESPONSES["error"])

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("FAQ", url="https://ciphex.io/")],
            [InlineKeyboardButton("Twitter", url="https://x.com/ciphexio")]
            # Add more buttons as needed
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text=BOT_RESPONSES["help"],
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    async def _handle_contract(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["contract_info"], parse_mode="Markdown")

    async def _handle_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Get live price data from API instead of Redis
        token_price = await self._get_live_price_data()
        
        if token_price and token_price != "Unknown":
            formatted_price = (
                f"**Current CPX Token Price**: {token_price}\n"
                f"Visit [presale.ciphex.io](https://presale.ciphex.io) for real-time pricing and to participate in the presale."
            )
            await update.message.reply_text(formatted_price, parse_mode="Markdown")
        else:
            # Fall back to cached data if API call fails
            stats_data_str = await self.cache_manager.redis.get("ciphex_stats")
            if stats_data_str:
                stats_data = json.loads(stats_data_str)
                token_price = stats_data.get('price', {}).get('raw', 'Unknown')
                
                formatted_price = (
                    f"**Current CPX Token Price**: {token_price} (cached)\n"
                    f"Visit [presale.ciphex.io](https://presale.ciphex.io) for real-time pricing and to participate in the presale."
                )
                await update.message.reply_text(formatted_price, parse_mode="Markdown")
            else:
                await update.message.reply_text(BOT_RESPONSES["price_info"], parse_mode="Markdown")

    async def _handle_whitepaper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(BOT_RESPONSES["whitepaper_info"], parse_mode="Markdown")
        
    async def _get_live_stats_data(self):
        """Fetch real-time stats data directly from the API"""
        url = "https://presale.ciphex.io/api/presale"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"API request failed with status code: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching live stats data: {e}")
            return None
            
    async def _get_live_price_data(self):
        """Fetch real-time price data directly from the API"""
        stats_data = await self._get_live_stats_data()
        if stats_data:
            return stats_data.get('price', {}).get('raw', "Unknown")
        return "Unknown"

    async def _handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Get live stats data from API
        stats_data = await self._get_live_stats_data()
        
        if stats_data:
            # Use the live data from the API response
            cipherions = stats_data.get('cipherions', 'Unknown')
            total_contributions = stats_data.get('totalContributions', {}).get('ui', 'Unknown')
            total_cpx_presold = stats_data.get('totalCPXPresold', {}).get('ui', 'Unknown')
            total_staked = stats_data.get('totalStaked', {}).get('ui', 'Unknown')
            percent_staked = stats_data.get('percentStaked', {}).get('ui', 'Unknown')

            formatted_stats = (
                f"**Community & Presale Stats**:\n"
                f"- Total Community Members: {cipherions}\n"
                f"- Total Funds Raised: {total_contributions}\n"
                f"- Total CPX Purchased: {total_cpx_presold}\n"
                f"- Total Staked: {total_staked}\n"
                f"- Percent Staked: {percent_staked}%\n"
            )
            await update.message.reply_text(formatted_stats, parse_mode="Markdown")
        else:
            # Fall back to cached data if API call fails
            stats_data_str = await self.cache_manager.redis.get("ciphex_stats")
            if stats_data_str:
                stats_data = json.loads(stats_data_str)
                cipherions = stats_data.get('cipherions', 'Unknown')
                total_contributions = stats_data.get('totalContributions', {}).get('ui', 'Unknown')
                total_cpx_presold = stats_data.get('totalCPXPresold', {}).get('ui', 'Unknown')
                total_staked = stats_data.get('totalStaked', {}).get('ui', 'Unknown')
                percent_staked = stats_data.get('percentStaked', {}).get('ui', 'Unknown')

                formatted_stats = (
                    f"**Community & Presale Stats (cached)**:\n"
                    f"- Total Community Members: {cipherions}\n"
                    f"- Total Funds Raised: {total_contributions}\n"
                    f"- Total CPX Purchased: {total_cpx_presold}\n"
                    f"- Total Staked: {total_staked}\n"
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
