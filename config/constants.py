BOT_RESPONSES = {
    "welcome": """Welcome to the official CipheX Telegram Channel! 🚀
I'm your Centurion assistant for all things CipheX.
Use /help to see what I can do for you.""",
    "help": """Available Commands:
/price - Check current token price 💰
/whitepaper - Access our whitepaper 📄
/contract - Show contract address 📝
/stats - View trading statistics 📊
/certik - View Certik audit status 🔒

You can also tag me (@CenturySupport) in any message to ask questions!""",
    "error": "I encountered an error. Please try again later.",
    "rate_limit": "Please wait a moment before sending another message.",
    "thinking": "Let me think about that... 🤔",
}

WHITEPAPER_SECTIONS = [
    "introduction",
    "tokenomics",
    "roadmap",
    "technology",
    "security",
]

ERROR_MESSAGES = {
    "scraping_error": "Error fetching latest data",
    "api_error": "External API error",
    "database_error": "Database connection error",
    "validation_error": "Data validation failed",
}
