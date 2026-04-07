import requests, sqlite3, json, time
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"

SEARCH_TERMS = [
    "AI agent", "autonomous agent", "virtuals", "bittensor",
    "eliza", "olas", "fetch ai", "defai", "agentfi",
]

def fetch_pairs(query):
    url = f"https://api.dexscreener.com/latest/dex/search?q={requests.utils.quote(query)}"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200:
            return r.json().get("pairs", [])
    except Exception as e:
        print(f"  Fel: {e}")
    return []

def save_pairs(pairs, query):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for p in pairs:
        try:
            base = p.get("baseToken", {})
            agent_id = f"dex-{p.get('chainId','')}-{p.get('pairAddress','')}"
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, chain,
                 token_address, token_symbol, market_cap_usd,
                 agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'dexscreener', ?, ?, ?, ?, ?, 'trading', ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    market_cap_usd=excluded.market_cap_usd,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                agent_id,
                base.get("name",""),
                p.get("chainId",""),
                base.get("address",""),
                base.get("symbol",""),
                p.get("marketCap") or p.get("fdv"),
                json.dumps({
                    "pair": p.get("pairAddress"),
                    "dex": p.get("dexId"),
                    "price_usd": p.get("priceUsd"),
                    "volume_24h": p.get("volume",{}).get("h24"),
                    "price_change_24h": p.get("priceChange",{}).get("h24"),
                    "query": query,
                }),
                now, now
            ))
            saved += 1
        except Exception as e:
            print(f"  DB-fel: {e}")
    conn.commit()
    conn.close()
    return saved

def run():
    print("=== DexScreener AI Agent Crawler ===")
    total = 0
    for term in SEARCH_TERMS:
        pairs = fetch_pairs(term)
        if pairs:
            saved = save_pairs(pairs, term)
            total += saved
            print(f"  '{term}': {len(pairs)} pairs → {saved} sparade")
        time.sleep(1)
    print(f"\nTotalt sparat: {total}")
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='dexscreener'").fetchone()[0]
    conn.close()
    print(f"DexScreener totalt i DB: {count}")

if __name__ == "__main__":
    run()
