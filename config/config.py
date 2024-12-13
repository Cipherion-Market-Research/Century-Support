import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Bot Configuration
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # Database Configuration
    MONGODB_URI = os.getenv("MONGODB_URI")
    REDIS_URL = os.getenv("REDIS_URL")

    # AI Configuration
    MAX_TOKENS = 150
    TEMPERATURE = 0.7
    MODEL = "gpt-3.5-turbo"

    # Website URLs for scraping
    WEBSITE_URLS = {
        "tokenomics": os.getenv("WEBSITE_TOKENOMICS_URL"),
        "roadmap": os.getenv("WEBSITE_ROADMAP_URL"),
        "about": os.getenv("WEBSITE_ABOUT_URL"),
    }

    # Certik Configuration
    CERTIK_URL = os.getenv("CERTIK_URL")

    # Sync Configuration
    SYNC_INTERVAL_HOURS = 6
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 60

    # Cache Configuration
    CACHE_EXPIRY = 3600  # 1 hour

    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE = 20