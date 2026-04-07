import requests, sqlite3, json
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
BASE_URL = "https://api.virtuals.io/api/virtuals"

def fetch_all():
    all_agents = []
    page = 1
    # Kolla först total count
    r = requests.get(f"{BASE_URL}?page=1&pageSize=1", timeout=10)
    d = r.json()
    total = d.get("total") or d.get("count") or d.get("pagination", {}).get("total", "?")
    print(f"  API total: {total}")
    print(f"  Pagination-nycklar: {[k for k in d.keys() if k not in ['data']]}")

    while True:
        try:
            # Prova olika pagination-parametrar
            url = f"{BASE_URL}?pagination[page]={page}&pagination[pageSize]=100"
            r = requests.get(url, timeout=15, headers={"Accept": "application/json"})
            d = r.json()
            items = d.get("data", [])
            if not items:
                break
            all_agents.extend(items)
            print(f"  Sida {page}: {len(items)} agenter (totalt: {len(all_agents)})")
            page += 1
            if len(items) < 100:
                break
        except Exception as e:
            print(f"  Fel: {e}")
            break
    return all_agents

def save_agents(agents):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for a in agents:
        try:
            agent_id = str(a.get("id") or a.get("uid", ""))
            name = a.get("name", "")
            token_addr = a.get("tokenAddress") or a.get("walletAddress", "")
            symbol = a.get("symbol", "")
            market_cap = a.get("mcapInVirtual") or a.get("fdvInVirtual")
            desc = a.get("description") or a.get("aidesc") or a.get("role", "")

            # creator kan vara dict eller string
            creator_raw = a.get("creator", "")
            if isinstance(creator_raw, dict):
                creator = creator_raw.get("walletAddress") or creator_raw.get("id") or str(creator_raw)
            else:
                creator = str(creator_raw) if creator_raw else ""

            chain = a.get("chain") or "base"

            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 token_address, token_symbol, market_cap_usd,
                 creator_address, agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'virtuals', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    market_cap_usd=excluded.market_cap_usd,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                f"virtuals-{agent_id}", name, desc[:500], chain,
                token_addr, symbol,
                float(market_cap) if market_cap else None,
                creator,
                a.get("category") or "trading",
                json.dumps(a), now, now
            ))
            saved += 1
        except Exception as e:
            print(f"  DB-fel: {e}")
    conn.commit()
    conn.close()
    return saved

def run():
    print("=== Virtuals Protocol Crawler ===")
    agents = fetch_all()
    print(f"Totalt hämtade: {len(agents)}")
    if agents:
        saved = save_agents(agents)
        print(f"Sparat: {saved} i DB")
        conn = sqlite3.connect(DB_PATH)
        total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='virtuals'").fetchone()[0]
        conn.close()
        print(f"Virtuals totalt i DB: {total}")

if __name__ == "__main__":
    run()
