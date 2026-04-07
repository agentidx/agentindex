import requests, sqlite3, json, time
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"

AI_CATEGORIES = [
    "ai-agents",
    "ai-framework", 
    "ai-applications",
    "ai-agent-launchpad",
    "ai-meme-coins",
    "defai",
    "artificial-intelligence",
]

def fetch_category(category_id):
    all_tokens = []
    page = 1
    while True:
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&category={category_id}&per_page=250&page={page}&order=market_cap_desc"
        try:
            r = requests.get(url, timeout=15, headers={"Accept":"application/json"})
            if r.status_code == 429:
                print(f"    Rate limit, väntar 60s...")
                time.sleep(60)
                continue
            if r.status_code != 200:
                break
            items = r.json()
            if not items:
                break
            all_tokens.extend(items)
            print(f"    Sida {page}: {len(items)} tokens")
            page += 1
            if len(items) < 250:
                break
            time.sleep(1.5)  # CoinGecko rate limit
        except Exception as e:
            print(f"    Fel: {e}")
            break
    return all_tokens

def save_tokens(tokens, category):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for t in tokens:
        try:
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 token_address, token_symbol, market_cap_usd,
                 agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'coingecko', ?, ?, 'multi', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    market_cap_usd=excluded.market_cap_usd,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                f"cg-{t['id']}",
                t.get("name",""),
                t.get("description",""),
                t.get("contract_address",""),
                t.get("symbol","").upper(),
                t.get("market_cap"),
                category,
                json.dumps({
                    "id": t.get("id"),
                    "symbol": t.get("symbol"),
                    "current_price": t.get("current_price"),
                    "market_cap": t.get("market_cap"),
                    "market_cap_rank": t.get("market_cap_rank"),
                    "price_change_24h": t.get("price_change_percentage_24h"),
                    "ath": t.get("ath"),
                    "category": category,
                }),
                now, now
            ))
            saved += 1
        except Exception as e:
            print(f"    DB-fel: {e}")
    conn.commit()
    conn.close()
    return saved

def run():
    print("=== CoinGecko AI Categories Crawler ===")
    total = 0
    seen_ids = set()
    
    for cat in AI_CATEGORIES:
        print(f"\nKategori: {cat}")
        tokens = fetch_category(cat)
        # Deduplicera
        new_tokens = [t for t in tokens if t['id'] not in seen_ids]
        seen_ids.update(t['id'] for t in tokens)
        print(f"  {len(tokens)} hämtade, {len(new_tokens)} nya (dedup)")
        if new_tokens:
            saved = save_tokens(new_tokens, cat)
            total += saved
            print(f"  Sparat: {saved}")
        time.sleep(2)
    
    print(f"\nTotalt sparat: {total}")
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='coingecko'").fetchone()[0]
    print(f"CoinGecko totalt i DB: {count}")
    
    print("\nTop 10 efter market cap:")
    top = conn.execute("""
        SELECT agent_name, token_symbol, market_cap_usd, agent_type
        FROM agent_crypto_profile WHERE source='coingecko'
        AND market_cap_usd IS NOT NULL
        ORDER BY market_cap_usd DESC LIMIT 10
    """).fetchall()
    for t in top:
        print(f"  {t[0]} ({t[1]}) — ${t[2]:,.0f} — {t[3]}")
    conn.close()

if __name__ == "__main__":
    run()
