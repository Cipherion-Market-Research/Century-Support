# 🤖 Century Support 🤖

Century Support is the platform behind Ciphex's community support experience.
It started as a single Telegram bot and has grown into a small set of
cooperating services: the bot itself, a core message-handling API, a KPI
sync service, a publications RAG (retrieval-augmented generation) service,
and a content/surface drift monitor. This repo hosts all of them.

## The Telegram Bot 🌟

The original piece: an AI-powered Telegram bot that answers questions about
Ciphex for the community, backed by cached FAQ/whitepaper context and live
data from official Ciphex endpoints.

- **Real-time Support**: Instant responses to user queries, tagging the bot
  (`@CiphexHelpBot`) in any message
- **AI-Powered Conversations**: Natural-language answers grounded in
  whitepaper/FAQ context — the bot never solicits purchases and always
  attaches risk disclaimers when discussing price or returns
- **Live Data**: `/price` and `/stats` call the Ciphex claim-portal API
  directly for current figures, falling back to a short-lived Redis cache
  if the API is unavailable
- **Command System**: Easy-to-use commands for quick access to information
- **Caching System**: Redis-backed response caching for improved performance

### Commands 📝

- `/start` - Initialize the bot and get a welcome message
- `/help` - Display available commands and features
- `/price` - Check the CPX contribution price and round status
- `/whitepaper` - Ask questions answered from the official whitepaper
- `/ca` - Show the CPX contract address & Etherscan link
- `/stats` - View claim-portal statistics
- `/audit` - View CertiK Skynet audit & security score info
- `/claim` - Access the token claiming portal
- `/website` - Link to the official Ciphex website

## The Platform's Other Services 🏗️

Beside the bot, this repo hosts four independent services that share the
same `facts.yaml` facts store and Redis-based contracts:

- **`century_core/`** — A FastAPI service that is the platform's core
  message-handling API (`POST /v1/messages`, `GET /v1/facts/:key`,
  `POST /v1/broadcasts`). It routes an inbound message to a command handler
  or to Q&A (facts store, KPI store, publications RAG) and, when needed, a
  guarded LLM call (OpenAI, model configurable, default `gpt-4o-mini`) with
  guardrails against purchase solicitation and invented numbers.
- **`kpi_sync/`** — A background polling service that reads Ciphex's
  claim-portal, marketing/key-metrics, and on-chain endpoints on a schedule
  and writes each value to Redis as a small JSON envelope (value, source,
  timestamps, TTL) so consumers can tell a fresh number from a stale one.
- **`pubs_rag/`** — Ingests Ciphex publications (PDFs and website pages)
  into Postgres with `pgvector`, chunked and embedded for retrieval with
  title/date/source citations. New publications arrive via a GitHub
  webhook and go through an approve/revoke workflow before they're served.
- **`drift_monitor/`** — Watches the Ciphex website and related product
  repos for content and surface changes, diffing them against a stored
  baseline. It only ever proposes changes (as a report or a PR) — it never
  edits `facts.yaml` automatically; a human always reviews before merge.

## Technical Architecture 🏗️

- **Core Framework**: Python with `python-telegram-bot` (bot) and FastAPI
  (`century_core`)
- **AI Integration**: OpenAI (`gpt-4o-mini` by default)
- **Database**: MongoDB for bot conversation history; Postgres + `pgvector`
  for publication embeddings (`pubs_rag`)
- **Caching / Messaging**: Redis for response caching and as the KPI
  envelope store shared across services
- **Document Parsing**: Whitepaper/PDF parsing for grounded answers
- **Testing**: Pytest with async support across all services

## Project Structure 📁

```
century-support-bot/
├── config/            # Bot configuration files
├── core/              # Core bot functionality
├── data/              # Training data and cache
├── scrapers/          # Whitepaper/PDF parsing modules
├── century_core/      # Core message-handling API (FastAPI)
├── kpi_sync/          # Tier-1 KPI polling service
├── pubs_rag/          # Publications RAG ingestion service
├── drift_monitor/     # Content/surface drift monitor
├── docs/              # Public integration contracts
├── tests/             # Test suite
├── utils/             # Utility functions
├── main.py            # Bot entry point
└── requirements.txt   # Dependencies
```

## Contributing 🤝

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules that govern changes to
`facts.yaml`, the platform's canonical facts store, and
[docs/CONTRACTS.md](docs/CONTRACTS.md) for the integration contracts shared
between services.

## Security 🔒

- Every service uses environment variables for sensitive data
- Rate limiting to prevent abuse
- Input validation and sanitization
- Regular security updates and dependency maintenance

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE)
file for details.

## Support 💬

For support, please join our [Telegram community](https://t.me/Ciphexgroup)
and tag @CenturySupport in your message.

## Acknowledgments 🙏

- OpenAI for AI integration
- Python Telegram Bot community
- Ciphex community for continuous feedback and support

---

Built with ❤️ by the Ciphex Team
