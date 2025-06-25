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
• Final Presale Price: ~$0.26 per CPX
• Visit [ciphex.io](https://ciphex.io) for the most current information.

The presale is currently open only to existing contributors and accredited investors.""",

		"whitepaper_info": """TLDR? Don't worry! I've studied the whitepaper from cover to cover and I'm here to help! 
  
Simply tag me (@CiphexHelpBot) with your question about any topic - like tokenomics, vesting schedules, or project details.

For example: "@CiphexHelpBot What does the whitepaper say about token supply?"

To access the full whitepaper, visit [Ciphex Whitepaper](https://ciphex.io/whitepapers)""",

		"stats_info": """**Community & Presale Stats**:
- Total Community Members (Wallets)
- Total Funds Raised (USD)
- Allocated for Presale: 142M tokens
- Total CPX Purchased (Staked)""",

		"presale_info": """**CipheX Presale Information:**

The CipheX Presale is no longer open to the general public and has transitioned to a private phase.

Key Details:
• Final Price: ~$0.26 per CPX
• Participation: Open to existing contributors and accredited investors only.

Unallocated presale tokens are reserved for private placements.

Visit [ciphex.io](https://ciphex.io) for more details.

⚠️ Important Reminders:
• Only use official links
• Never share wallet seed phrases
• CipheX team will never DM you first""",

		"data_info": """Data updates regularly. Check:
[Community Stats](https://presale.ciphex.io)
[CPX Contract](https://etherscan.io/address/0x18b33687d1c804Dd4ea6c82106e54923c23a652E)
[Presale Contract](https://etherscan.io/address/0x28995579fdf4F1Ea01ba54b6F4f0524cE63Ff1bc)""",
    
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

COMPOSITE_SECTIONS = [
    "CipheX Capital Ecosystem Overview",
    "Ecosystem Operations",
    "Governance & Compliance",
    "Market Execution Fees",
    "CipheX Tokenomics & Presale",
    "The Alpha Centurion Network (Alpha CPX)",
    "Cipherion Market Research Group (CMR)",
    "Real-World Asset Tokenization (RWA)",
    "Alpha CPX Frequently Asked Questions (FAQs)",
    "General Contact Information"
]

# Topic to Section Mapping
TOPIC_SECTIONS = {
    "market_centurions": ["The Alpha Centurion Network (Alpha CPX)"],
    "abacus": ["Cipherion Market Research Group (CMR)"],
    "tokenomics": ["CipheX Tokenomics & Presale"],
    "presale": ["CipheX Tokenomics & Presale"],
    "staking": ["Ecosystem Operations"],
    "governance": ["Governance & Compliance"],
    "treasury": ["CipheX Tokenomics & Presale"],
    "risks": ["Real-World Asset Tokenization (RWA)"],
    "contact": ["General Contact Information"]
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