"""
Nerq Crypto Module — Configuration
Reads API keys from environment variables or .env file.
"""

import os
from pathlib import Path

# Try loading .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# CoinGecko
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_RATE_LIMIT = 30  # calls per minute (Demo plan)

# DeFiLlama (no key needed — public API)
DEFILLAMA_BASE_URL = "https://api.llama.fi"

# Database
CRYPTO_DB_PATH = os.getenv(
    "CRYPTO_DB_PATH",
    str(Path(__file__).parent.parent / "data" / "crypto_trust.db")
)

# Crawl settings
CRAWL_BATCH_SIZE = 250          # coins per CoinGecko /markets call (max 250)
CRAWL_DELAY_SECONDS = 2.1       # ~28 calls/min, safely under 30/min limit
CRAWL_MAX_PAGES = 60            # 60 * 250 = 15,000 tokens coverage
