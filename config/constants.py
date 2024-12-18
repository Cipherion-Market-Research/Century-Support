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
Currently not live. Once active, you can visit [CipheX](https://ciphex.io/) to purchase CPX tokens.
Stay tuned for announcements! We will post updates here and on our [Twitter](https://x.com/ciphexio).""",

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
    "adoption of cryptocurrency": "1.2 Adoption of Cryptocurrency",
    "competitive landscape": "1.3 Competitive Landscape",
    "the rise of generative ai": "1.4 The Rise of Generative AI",
    "the community": "2.1 The Community",
    "future use cases and long-term utility": "2.2 Future Use Cases and Long-Term Utility",
    "creators & founding contributors": "2.3 Creators & Founding Contributors",
    "consensus and governance": "2.4 Consensus and Governance",
    "regulatory and financial oversight": "2.5 Regulatory and Financial Oversight",
    "privacy of members and contributors": "2.6 Privacy of Members and Contributors",
    # Removed duplicates and added missing sections
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
    "adoption of cryptocurrency": "1.2 Adoption of Cryptocurrency",
    "competitive landscape": "1.3 Competitive Landscape",
    "the rise of generative ai": "1.4 The Rise of Generative AI",
    "the community": "2.1 The Community",
    "future use cases and long-term utility": "2.2 Future Use Cases and Long-Term Utility",
    "creators & founding contributors": "2.3 Creators & Founding Contributors",
    "consensus and governance": "2.4 Consensus and Governance",
    "regulatory and financial oversight": "2.5 Regulatory and Financial Oversight",
    "privacy of members and contributors": "2.6 Privacy of Members and Contributors",
    # Removed duplicates
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

If you wish to contact us, please email us at help@ciphex.io"""
}