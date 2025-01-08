BOT_RESPONSES = {
	"welcome": """Welcome to the official CipheX Telegram Channel! 🚀

I'm your Centurion Assistant for all things CipheX. 
Tag me (@CiphexHelpBot) in any message to ask questions or use /help to see what I can do for you.

⚠️ Important: ⚠️
• CipheX will never DM you first
• Never share your wallet seed phrases
• Always verify links through official channels""",

    "help": """**Available Commands:**
/whitepaper - Access our official whitepaper 📄  
/website - Access our official website 🌐  
/ca - Show contract address & Etherscan link 📝  
/presale - Check presale status 💵
/audit - View Certik audit & Skynet scores 📖

You can also tag me (@CiphexHelpBot) in any message to ask questions!""",

		"error": "I encountered an error. Please try again later.",
		"rate_limit": "Please wait a moment before sending another message.",
		"thinking": "Let me think about that... 🤔",

		"contract_info": """**CipheX (CPX) Contract Address:**
`0x18b33687d1c804Dd4ea6c82106e54923c23a652E`

View on [Etherscan](https://etherscan.io/token/0x18b33687d1c804Dd4ea6c82106e54923c23a652E)""",

		"price_info": """**Token Price**:
The current CPX token price updates regularly. Visit [Ciphex](https://ciphex.io/) to see the latest price.""",

		"whitepaper_info": """TLDR? Don't worry! I've studied the whitepaper from cover to cover and I'm here to help! 
  
Simply tag me (@CiphexHelpBot) with your question about any topic - like tokenomics, vesting schedules, or project details.

For example: "@CiphexHelpBot What does the whitepaper say about token supply?"

To access the full whitepaper, visit [Ciphex Whitepaper](https://ciphex.io/whitepaper.pdf)""",

		"stats_info": """**Community & Presale Stats**:
- Total Community Members (Wallets)
- Total Funds Raised (USD)
- Allocated for Presale: 142M tokens
- Total CPX Purchased (Staked)""",

		"presale_info": """**CipheX Public Presale**:
Launching January 24, 2025! 🚀

Key Details:
• Starting Price: $0.10 per CPX
• Minimum Purchase: 2,000 CPX
• Duration: 180 days
• Target Funding: $20M
• Accepted Payments: USDT, USDC, ETH

The price will increase automatically every 24 hours during the presale period, with potential gains up to 159.93% by the end.

Visit [CipheX](https://ciphex.io) to participate when live.

⚠️ Important Reminders:
• Only use official links
• Never share wallet seed phrases
• CipheX team will never DM you first""",

		"data_info": """Data updates regularly. Check:
[Community Stats](https://ciphex.io/#community)
[CPX Contract](https://etherscan.io/address/0x18b33687d1c804Dd4ea6c82106e54923c23a652E)
[Presale Contract](https://etherscan.io/address/0x28995579fdf4F1Ea01ba54b6F4f0524cE63Ff1bc)
[Staking Contract](https://etherscan.io/address/0xc3c0654172125E0e7001Af78Ead58190f4e50c6A)""",
    
    "certik_info": """**[Certik Skynet](https://skynet.certik.com/projects/ciphex)**:
View our project page on Skynet for detailed audit reports and security scores.""",

    "website_info": """**[https://ciphex.io](https://ciphex.io)**:
Visit our official website for the latest updates, news, and information."""
}

WHITEPAPER_MAP = {
    "introduction": "1.0 Introduction",
    "ciphex ecosystem": "1.1 The CipheX Ecosystem",
    "origin": "1.2 The Origin of CipheX",
    "autonomous trading": "1.3 Autonomous Market Trading",
    "future": "1.4 The Future of CipheX",
    "roadmap": "1.5 Road Map Overview",
    "tokenomics": "2.0 Tokenomics",
    "max supply": "2.1 CipheX Maximum Supply",
    "creator tokens": "2.2 Creator & Founder Tokens",
    "treasury": "2.3 Treasury Management",
    "presale": "2.4 PreSale of CPX Tokens",
    "pricing": "2.5 Automated Daily Pricing",
    "presale costs": "2.6 Costs of PreSale Activities",
    "use of proceeds": "2.7 Planned Use of Proceeds",
    "lockup": "2.8 CPX Lockup Restrictions",
    "vesting": "2.9 CPX Vesting Schedule",
    "staking": "2.10 Fixed Term Staking and Rewards",
    "staking redemptions": "2.11 Fixed Term Staking Redemptions",
    "community management": "3.0 Community Management",
    "hybrid model": "3.1 Hybrid Organizational Model",
    "capital reserves": "3.2 Operating Capital Reserves",
    "investment": "3.3 Investment Participation",
    "returns": "3.4 Distribution of Returns",
    "creators": "3.5 Creators & Founding Contributors",
    "contributors": "3.6 General and Expert Contributors",
    "rewards": "3.7 Market Performance Rewards",
    "removals": "3.8 Removals and Termination",
    "voting": "3.9 Eligibility for Community Voting",
    "buyback": "3.10 CPX Token Buyback Program",
    "burn program": "3.11 Total Supply Burn Program",
    "performance": "4.0 Performance Benchmarks",
    "revenue streams": "4.1 CipheX Revenue Streams",
    "growth": "4.2 Market Returns and Revenue Growth",
    "scalability": "4.3 Scalable Growth and Efficiency",
    "risks": "5.0 Market Risk Factors"
}

WHITEPAPER_SECTIONS = WHITEPAPER_MAP.copy()  # Since they're identical now

ERROR_MESSAGES = {
    "scraping_error": "Error fetching latest data",
    "api_error": "External API error",
    "database_error": "Database connection error",
    "validation_error": "Data validation failed",
}

SCHEDULED_MESSAGES = {
    "privacy_reminder": "Adjust your Telegram Privacy Settings & Avoid Spam Calls:\n\n• Change Calls to Contacts only\n• Set New Chats from Unknown Users to Archive and Mute\n• Set Who Can Add You to Groups to Nobody 👮",
    
    "admin_warning": """Friendly reminder: CipheX Admins will NEVER DM you. Please do not respond to anyone claiming they are from our team. It is a scam!

If you wish to contact us, please email us at help@ciphex.io""",

    "start_message": """👋 Welcome to Century Support Bot!

I'm here to help you with all things CipheX. Use commands like:
📊 /price - Check current token price
📄 /whitepaper - Access whitepaper
🔍 /stats - View trading statistics

Need help? Just ask or use /help for all commands!"""
}