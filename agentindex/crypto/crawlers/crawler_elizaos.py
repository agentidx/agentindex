import requests, sqlite3, json
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"

def fetch_elizaos():
    """ElizaOS exponerar agent-registry via GitHub"""
    sources = [
        "https://raw.githubusercontent.com/elizaOS/eliza/main/characters/trump.character.json",
        "https://api.github.com/repos/elizaOS/eliza/contents/characters",
        "https://api.github.com/repos/elizaOS/characterfile/contents",
        "https://raw.githubusercontent.com/elizaOS/agents/main/registry.json",
        "https://api.github.com/repos/elizaOS/agents/contents",
    ]
    for url in sources:
        try:
            r = requests.get(url, timeout=10, headers={"Accept":"application/json", "User-Agent":"ZARQ-Crawler/1.0"})
            print(f"  {url} → {r.status_code} | {r.text[:200]}")
        except Exception as e:
            print(f"  {url} → ERR: {e}")

def run():
    print("=== ElizaOS Crawler ===")
    fetch_elizaos()

if __name__ == "__main__":
    run()
