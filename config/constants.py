BOT_RESPONSES = {
	"welcome": """Welcome to the official CipheX Telegram Channel! 🚀
I'm your Centurion assistant for all things CipheX.
Use /help to see what I can do for you.""",
    "help": """**Available Commands:**
/whitepaper - Access our whitepaper 📄  
/contract - Show contract address & Etherscan link 📝  
/stats - View community & presale statistics 📊
/presale - Check presale status 💵
/certik - View Certik audit report 📖

**Other Resources:**
- [Ciphex Website](https://ciphex.io)
- [FAQ](https://ciphex.io/#faq) 
- [Twitter](https://x.com/ciphexio)

Tag me (@CiphexHelp) in any message to ask questions!""",

		"error": "I encountered an error. Please try again later.",
		"rate_limit": "Please wait a moment before sending another message.",
		"thinking": "Let me think about that... 🤔",

		"contract_info": """**CipheX (CPX) Contract Address:**
`0x18b33687d1c804Dd4ea6c82106e54923c23a652E`

View on [Etherscan](https://etherscan.io/token/0x18b33687d1c804Dd4ea6c82106e54923c23a652E)""",

		"price_info": """**Token Price**:
The current CPX token price updates regularly. Visit the [Ciphex](https://ciphex.io/) to see the latest price.""",

		"whitepaper_info": """I've studied the whitepaper from cover to cover. Ask me anything specific and I'll do my best to answer.
For the full whitepaper, visit [Ciphex Whitepaper](https://ciphex.io/whitepaper.pdf)""",

		"stats_info": """**Community & Presale Stats**:
- Total Community Members (Wallets)
- Total Funds Raised (USD)
- Allocated for Presale: 142M tokens
- Total CPX Purchased (Staked)""",

		"presale_info": """**CipheX Public Presale**:
Currently not live. Once active, you can visit [CipheX](https://ciphex.io/) to purchase CPX tokens.
Stay tuned for announcements! We will post updates here and on our [Twitter](https://x.com/ciphexio).""",

		"data_info": """
Data updates regularly. Check:
[Community Stats](https://ciphex.io/#community) or
[CPX Contract](https://etherscan.io/address/0x18b33687d1c804Dd4ea6c82106e54923c23a652E)
[Presale Contract](https://etherscan.io/address/0x28995579fdf4F1Ea01ba54b6F4f0524cE63Ff1bc)
[Staking Contract](https://etherscan.io/address/0xc3c0654172125E0e7001Af78Ead58190f4e50c6A)""",
    
    "certik_info": """**Certik Audit**:
View our Certik Skynet page for detailed audit reports and security metrics:
[Certik Skynet](https://skynet.certik.com/projects/ciphex)"""
}


WHITEPAPER_MAP = {
    "introduction": "1.0 Introduction",
    "what is cpx": "1.1 What is Cipherion CipheX",
    "tokenomics": "3.0 Tokenomics",
    "vesting": "3.11 Vesting Schedules",
    "lockup": "3.10 Lockup Restrictions",
    "roadmap": "2.7 CipheX Road Map Overview",
    "technology": "6.0 Technology Overview",
    "asset and risk management": "5.4 Asset and Risk Management",
    "community": "2.0 CipheX Community",
    "max supply": "3.1 CipheX Maximum Supply",
    "hypatia": "6.6 Abacus and Market Centurions",
}

WHITEPAPER_SECTIONS = {
    "introduction": "1.0 Introduction",
    "what is cpx": "1.1 What is Cipherion CipheX",
    "tokenomics": "3.0 Tokenomics",
    "vesting": "3.11 Vesting Schedules",
    "lockup": "3.10 Lockup Restrictions",
    "roadmap": "2.7 CipheX Road Map Overview",
    "technology": "6.0 Technology Overview",
    "asset and risk management": "5.4 Asset and Risk Management",
    "community": "2.0 CipheX Community",
    "max supply": "3.1 CipheX Maximum Supply",
    "hypatia": "6.6 Abacus and Market Centurions",
}

ERROR_MESSAGES = {
    "scraping_error": "Error fetching latest data",
    "api_error": "External API error",
    "database_error": "Database connection error",
    "validation_error": "Data validation failed",
}
