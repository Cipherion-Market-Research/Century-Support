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

		"price_info": """**CPX Token Price Information:**
• Starting Price: $0.10 per CPX
• Visit [ciphex.io](https://ciphex.io) for real-time pricing

The price increases automatically every 24 hours during the presale period.""",

		"whitepaper_info": """TLDR? Don't worry! I've studied the whitepaper from cover to cover and I'm here to help! 
  
Simply tag me (@CiphexHelpBot) with your question about any topic - like tokenomics, vesting schedules, or project details.

For example: "@CiphexHelpBot What does the whitepaper say about token supply?"

To access the full whitepaper, visit [Ciphex Whitepaper](https://ciphex.io/whitepaper.pdf)""",

		"stats_info": """**Community & Presale Stats**:
- Total Community Members (Wallets)
- Total Funds Raised (USD)
- Allocated for Presale: 142M tokens
- Total CPX Purchased (Staked)""",

		"presale_info": """**CipheX Public Presale - NOW LIVE! 🚀**

Key Details:
• Starting Price: $0.10 per CPX
• Minimum Purchase: 2,000 CPX
• Duration: 180 days
• Target Funding: $20M
• Accepted Payments: USDT, USDC, ETH

The price increases automatically every 24 hours during the presale period.

Visit [ciphex.io](https://ciphex.io) to participate now and see the current price!

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
Visit our official website for the latest updates, news, and information.""",

    "contact_info": """**Contact CipheX Support:**

• Email: support@ciphex.io
• Website Support: https://ciphex.io/
• Telegram: @CipheXChannel (announcements only)

⚠️ **Important Security Reminders:**
• CipheX team will NEVER DM you first
• Only use official email and website
• Never share wallet seed phrases
• Verify all links through official channels

For technical support or general inquiries, please email support@ciphex.io"""
}

WHITEPAPER_SECTIONS = {
    # Introduction & Core Concepts
    "1.0": "CipheX Ecosystem",
    "1.1": "The Problem",
    "1.2": "The CipheX Mission",
    "1.3": "Crypto Markets Simplified",
    "1.4": "Centurion Market Advantage",
    "1.5": "The CipheX Roadmap",
    
    # Tokenomics
    "2.0": "Tokenomics",
    "2.1": "CipheX Maximum Supply",
    "2.2": "Creator & Founder Tokens",
    "2.3": "Treasury Management",
    "2.4": "PreSale of CPX Tokens",
    "2.5": "Costs of PreSale Activities",
    "2.6": "Lockup & Vesting Restrictions",
    "2.7": "Use of Presale Contributions",
    "2.8": "Fixed Term Staking and Rewards",
    
    # Community & Management
    "3.0": "The CipheX Community",
    "3.1": "Operating Capital Reserves",
    "3.2": "Eligibility for Community Voting",
    "3.3": "Creators & Community Contributors",
    "3.4": "Removals and Termination",
    "3.5": "Pre-Launch Centurion Trading",
    "3.6": "Pre-Launch Loss Coverage",
    "3.7": "Centurion Commercial Launch",
    "3.8": "Liquidity Pool & Trading Fees",
    "3.9": "Distribution of Market Returns",
    "3.10": "Buyback & Burn Program",
    "3.11": "CipheX Revenue Streams",
    
    # Performance & Risk
    "4.0": "Market Risk Factors",
    "4.1": "Market and Technical Volatility",
    "4.2": "Market Liquidity",
    "4.3": "Market and Price Manipulation",
    "4.4": "Privacy and Data Vulnerabilities",
    "4.5": "Operational Risks",
}

# Topic to Section Mapping
TOPIC_SECTIONS = {
    "market_centurions": ["1.2", "1.3", "5.2"],  # Sections about Market Centurions
    "abacus": ["1.1", "1.2", "1.3"],  # Sections about Abacus Network
    "tokenomics": ["2.0", "2.1", "2.2", "2.3", "2.4"],
    "presale": ["2.4", "2.5", "2.6"],
    "staking": ["2.10", "2.11"],
    "governance": ["3.0", "3.1", "3.9"],
    "treasury": ["2.3", "3.2"],
    "risks": ["5.0", "5.1", "5.2", "5.3", "5.4", "5.5"],
    "contact": ["3.0", "3.1"]  # Community Management sections
}

ERROR_MESSAGES = {
    "scraping_error": "Error fetching latest data",
    "api_error": "External API error",
    "database_error": "Database connection error",
    "validation_error": "Data validation failed",
}

SCHEDULED_MESSAGES = {
    "privacy_reminder": "Adjust your Telegram Privacy Settings & Avoid Spam Calls:\n\n• Change Calls to Contacts only\n• Set New Chats from Unknown Users to Archive and Mute\n• Set Who Can Add You to Groups to Nobody 👮",
    
    "admin_warning": """Friendly reminder: CipheX Admins will NEVER DM you. Please do not respond to anyone claiming they are from our team. It is a scam!

If you wish to contact us, please email us at support@ciphex.io""",

    "start_message": """👋 Welcome to Century Support Bot!

I'm here to help you with all things CipheX. Use commands like:
📊 /price - Check current token price
📄 /whitepaper - Access whitepaper
🔍 /stats - View trading statistics

Need help? Just ask or use /help for all commands!"""
}

# Technical topic mappings with relationships
TECHNICAL_SECTIONS = {
    "abacus": {
        "sections": ["1.1", "1.2", "1.3"],  # Core Abacus sections
        "related_topics": ["market_centurions", "autonomous_trading", "risk_management"],
        "keywords": [
            "abacus", "neural center", "analytics", "predictive", 
            "ai system", "machine learning", "quantitative"
        ]
    },
    "market_centurions": {
        "sections": ["1.2", "1.3", "5.2"],  # Centurions sections
        "related_topics": ["abacus", "autonomous_trading", "risk_management"],
        "keywords": [
            "centurion", "trading bot", "automated trading", 
            "market bot", "trading system"
        ]
    },
    "autonomous_trading": {
        "sections": ["1.3", "5.2", "5.3"],  # Trading sections
        "related_topics": ["abacus", "market_centurions", "risk_management"],
        "keywords": [
            "autonomous", "automated", "self-operating", 
            "ai trading", "algorithmic"
        ]
    },
    "risk_management": {
        "sections": ["5.1", "5.2", "5.3", "5.4"],  # Risk sections
        "related_topics": ["market_centurions", "autonomous_trading"],
        "keywords": [
            "risk", "volatility", "security", "protection", 
            "safeguard", "failsafe"
        ]
    }
}

TECHNICAL_DETAILS = {
    "neural_center": {
        "processing": [
            "Real-time market data analysis",
            "Pattern recognition algorithms",
            "Predictive modeling systems"
        ],
        "adaptations": [
            "Dynamic strategy adjustment",
            "Risk threshold management",
            "Market condition response"
        ],
        "failsafes": [
            "Automatic circuit breakers",
            "Multi-layer validation",
            "Emergency shutdown protocols"
        ]
    },
    "market_centurions": {
        "operations": [
            "Autonomous trade execution",
            "Cross-exchange arbitrage",
            "Liquidity optimization"
        ],
        "risk_controls": [
            "Position size limits",
            "Volatility-based adjustments",
            "Exposure management"
        ],
        "integration": [
            "Real-time Abacus feedback",
            "Multi-market coordination",
            "Adaptive strategy deployment"
        ]
    },
    "autonomous_trading": {
        "strategies": [
            "Market making protocols",
            "Statistical arbitrage",
            "Trend following systems"
        ],
        "safeguards": [
            "Risk exposure limits",
            "Market impact controls",
            "Drawdown protection"
        ],
        "monitoring": [
            "Real-time performance tracking",
            "Risk metric analysis",
            "System health checks"
        ]
    },
    "risk_management": {
        "protocols": [
            "Multi-signature controls",
            "Tiered authorization levels",
            "Emergency intervention systems"
        ],
        "monitoring": [
            "Real-time risk assessment",
            "Exposure tracking",
            "Compliance verification"
        ],
        "responses": [
            "Automated risk mitigation",
            "Position rebalancing",
            "System parameter adjustment"
        ]
    },
    "black_swan": {
        "coordination": [
            "Cross-system emergency protocols",
            "Integrated risk management response",
            "Multi-layer system coordination"
        ],
        "responses": [
            "Automated circuit breakers",
            "System-wide risk adjustments",
            "Emergency liquidity management"
        ]
    }
}