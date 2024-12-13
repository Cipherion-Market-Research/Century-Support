# 🤖 Century Support 🤖

Century Support Bot is an AI-powered Telegram bot designed to provide real-time support and information about CipheX to our community. The bot leverages OpenAI's GPT model to deliver accurate, context-aware responses while maintaining up-to-date information through automated web scraping.

## Features 🌟

- **Real-time Support**: Instant responses to user queries
- **AI-Powered Conversations**: Natural language processing using OpenAI's GPT model
- **Live Data Integration**: Automated scraping of latest information from:
  - CipheX Website
  - Certik Audit Status
  - Tokenomics Updates
  - Project Roadmap
- **Command System**: Easy-to-use commands for quick access to information
- **Caching System**: Efficient response caching for improved performance

## Commands 📝

- `/start` - Initialize the bot and get welcome message
- `/help` - Display available commands and features
- `/price` - Check current token price
- `/whitepaper` - Access whitepaper information
- `/contract` - Display contract address
- `/stats` - View trading statistics
- `/certik` - Check Certik audit status

## Technical Architecture 🏗️

- **Core Framework**: Python with `python-telegram-bot`
- **AI Integration**: OpenAI GPT-3.5
- **Database**: MongoDB for conversation history
- **Caching**: Redis for response caching
- **Web Scraping**: Async scraping with `aiohttp` and `BeautifulSoup4`
- **Testing**: Pytest with async support

## Project Structure 📁

```
century-support-bot/
├── config/            # Configuration files
├── core/              # Core bot functionality
├── data/              # Training data and cache
├── scrapers/          # Web scraping modules
├── tests/             # Test suite
├── utils/             # Utility functions
├── main.py            # Entry point
└── requirements.txt   # Dependencies
```

## Contributing 🤝

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Security 🔒

- The bot uses environment variables for sensitive data
- Implements rate limiting to prevent abuse
- Includes input validation and sanitization
- Regular security updates and dependency maintenance

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support 💬

For support, please join our [Telegram community](https://t.me/Ciphexgroup) and tag @CenturySupport in your message.

## Acknowledgments 🙏

- OpenAI for GPT integration
- Python Telegram Bot community
- CipheX community for continuous feedback and support

---

Built with ❤️ by the CipheX Team
