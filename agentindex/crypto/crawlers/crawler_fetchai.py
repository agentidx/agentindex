import os, requests, sqlite3, json, time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/Users/anstudio/agentindex/.env")
DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
API_KEY = os.getenv("AGENTVERSE_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json", "Content-Type": "application/json"}
SORT_MODES = ["relevancy", "created-at", "interactions", "last-modified"]

def fetch_by_sort(sort_mode):
    agents = []
    offset = 0
    limit = 100
    search_id = None

    while True:
        body = {"limit": limit, "offset": offset, "sort": sort_mode}
        if search_id:
            body["search_id"] = search_id

        r = requests.post("https://agentverse.ai/v1/search/agents",
                         headers=HEADERS, json=body, timeout=15)
        if r.status_code != 200:
            print(f"  Fel {r.status_code}")
            break

        d = r.json()
        if not search_id:
            search_id = d.get("search_id")

        batch = d.get("agents", [])
        if not batch:
            break

        agents.extend(batch)
        total = d.get("total", 0)
        offset += limit
        if offset >= min(total, 10000):
            break
        time.sleep(0.2)

    print(f"  sort={sort_mode}: {len(agents)} hämtade")
    return agents

def save_agents(agents):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for a in agents:
        try:
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 creator_address, agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'fetchai', ?, ?, 'fetch', ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                f"fetchai-{a['address']}",
                a.get("name", ""),
                a.get("description", ""),
                a.get("owner", ""),
                a.get("category") or a.get("type", "utility"),
                json.dumps({
                    "address": a.get("address"),
                    "protocols": a.get("protocols", []),
                    "total_interactions": a.get("total_interactions"),
                    "rating": a.get("rating"),
                    "status": a.get("status"),
                    "category": a.get("category"),
                    "domain": a.get("domain"),
                    "last_updated": a.get("last_updated"),
                }),
                now, now
            ))
            saved += 1
        except Exception as e:
            pass
    conn.commit()
    conn.close()
    return saved

def run():
    print("=== Fetch.ai Agentverse Crawler (multi-sort) ===")
    all_agents = []
    seen = set()

    for sort in SORT_MODES:
        batch = fetch_by_sort(sort)
        new = [a for a in batch if a["address"] not in seen]
        seen.update(a["address"] for a in batch)
        all_agents.extend(new)
        print(f"  Nya unika: {len(new)} | Totalt unika: {len(all_agents)}")

    print(f"\nTotalt unika agenter: {len(all_agents)}")
    saved = save_agents(all_agents)
    print(f"Sparat: {saved} i DB")

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='fetchai'").fetchone()[0]
    conn.close()
    print(f"Fetchai totalt i DB: {total}")

if __name__ == "__main__":
    run()
