"""Configuration management."""
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NERQ_MIN_TRUST = int(os.getenv("NERQ_MIN_TRUST", "70"))
NERQ_API_URL = os.getenv("NERQ_API_URL", "https://nerq.ai")
