"""
AgentVerse Crawler v2 — fetches agents from agentverse.ai (Fetch.ai)
Improved version: multi-sort, higher limits, no API key required for search.
Source: POST https://agentverse.ai/v1/search/agents
Stores into agent_crypto_profile table (source='agentverse').
"""
import requests, sqlite3, json, time
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
API_URL = "https://agentverse.ai/v1/search/agents"
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
SORT_MODES = ["relevancy", "created-at", "interactions", "last-modified"]


def fetch_by_sort(sort_mode, max_pages=100):
    agents = []
    offset = 0
    limit = 100
    search_id = None

    while offset < limit * max_pages:
        body = {"limit": limit, "offset": offset, "sort": sort_mode}
        if search_id:
            body["search_id"] = search_id

        try:
            r = requests.post(API_URL, headers=HEADERS, json=body, timeout=15)
            if r.status_code != 200:
                print(f"  Error {r.status_code} at offset {offset}")
                break
        except Exception as e:
            print(f"  Request error: {e}")
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
        time.sleep(0.3)

    print(f"  sort={sort_mode}: {len(agents)} fetched")
    return agents


def save_agents(agents):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for a in agents:
        address = a.get("address", "")
        if not address:
            continue
        agent_id = f"agentverse-{address}"
        name = a.get("name", "")
        desc = a.get("description", "")
        owner = a.get("owner", "")
        category = a.get("category") or a.get("type", "utility")
        domain = a.get("domain", "")

        try:
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 creator_address, agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'agentverse', ?, ?, 'fetch', ?, 'agent', ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    description=excluded.description,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                agent_id,
                name,
                desc[:2000],
                owner,
                json.dumps({
                    "address": address,
                    "protocols": a.get("protocols", []),
                    "total_interactions": a.get("total_interactions"),
                    "rating": a.get("rating"),
                    "status": a.get("status"),
                    "category": category,
                    "domain": domain,
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
    print("=== AgentVerse Crawler v2 ===")
    all_agents = []
    seen = set()

    for sort in SORT_MODES:
        batch = fetch_by_sort(sort)
        new = [a for a in batch if a.get("address") and a["address"] not in seen]
        seen.update(a["address"] for a in batch if a.get("address"))
        all_agents.extend(new)
        print(f"  New unique: {len(new)} | Total unique: {len(all_agents)}")

    print(f"\nTotal unique agents: {len(all_agents)}")
    saved = save_agents(all_agents)
    print(f"Saved: {saved}")

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='agentverse'").fetchone()[0]
    conn.close()
    print(f"AgentVerse total in DB: {total}")


if __name__ == "__main__":
    run()
