BOT_RESPONSES = {
    "welcome": """Welcome to the official CipheX Telegram Channel! 🚀
I'm your Centurion assistant for all things CipheX.
Use /help to see what I can do for you.""",
    "help": """**Available Commands:**
/price - Check current token price 💰  
/whitepaper - Access our whitepaper 📄  
/contract - Show contract address & Etherscan link 📝  
/stats - View community & presale statistics 📊

**Other Resources:**
- [Ciphex Website](https://ciphex.io)
- [FAQ](https://ciphex.io/#faq)
- [Twitter/X](https://x.com/ciphexio)

Tag me (@CipheXHelp) in any message to ask questions!""",
    "error": "I encountered an error. Please try again later.",
    "rate_limit": "Please wait a moment before sending another message.",
    "thinking": "Let me think about that... 🤔",
    "contract_info": """**CipheX (CPX) Contract Address:**
`0x18b33687d1c804Dd4ea6c82106e54923c23a652E`

View on [Etherscan](https://etherscan.io/token/0x18b33687d1c804Dd4ea6c82106e54923c23a652E)""",
    "price_info": """**Token Price:**
The current CPX token price updates regularly. Visit the [Ciphex Presale Widget](https://ciphex.io/) to see the latest price.""",
    "whitepaper_info": """You can find specific sections of the whitepaper from our training data.
For the full whitepaper, visit [Ciphex Whitepaper](https://ciphex.io/whitepaper.pdf)""",
    "stats_info": """**Community & Presale Stats**:
- Total Community Members (Wallets)
- Total Presale Contributions (USD)
- Total CPX Allocated to Public Presale: 142M tokens
- Total CPX Purchased in Presale (Staked)
- Percentage Staked vs Allocated

Data updates regularly. Check:
[Website Stats](https://ciphex.io/#community) or
[Presale Contract on Etherscan](https://etherscan.io/address/0x18b33687d1c804Dd4ea6c82106e54923c23a652E)
[Presale Proxy](https://etherscan.io/address/0x28995579fdf4F1Ea01ba54b6F4f0524cE63Ff1bc)
[Staking Proxy](https://etherscan.io/address/0xc3c0654172125E0e7001Af78Ead58190f4e50c6A)""",
    "certik_info": """**Certik Audit:**
View our Certik Skynet page for detailed audit reports and security metrics:
[Certik Skynet](https://skynet.certik.com/projects/ciphex)"""
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
