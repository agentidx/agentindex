"""
Official MCP Registry Crawler — fetches servers from registry.modelcontextprotocol.io
Source: https://registry.modelcontextprotocol.io/v0.1/servers
Stores into agent_crypto_profile table (source='mcp_registry').
3,399+ unique servers with version=latest pagination.
"""
import requests, sqlite3, json, time
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
API_URL = "https://registry.modelcontextprotocol.io/v0.1/servers"


def fetch_servers():
    all_entries = []
    cursor = None
    page = 0

    while True:
        params = {"limit": 100, "version": "latest"}
        if cursor:
            params["cursor"] = cursor

        try:
            r = requests.get(API_URL, params=params, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"  Request error at page {page}: {e}")
            break

        data = r.json()
        batch = data.get("servers", [])
        metadata = data.get("metadata", {})

        if not batch:
            break

        all_entries.extend(batch)
        page += 1
        cursor = metadata.get("nextCursor")
        if page % 10 == 0:
            print(f"  Fetched {len(all_entries)} entries ({page} pages)...")

        if not cursor:
            break
        time.sleep(0.2)

    print(f"Fetched {len(all_entries)} entries from MCP Registry ({page} pages)")

    # Deduplicate by name (keep latest version)
    unique = {}
    for entry in all_entries:
        srv = entry.get("server", {})
        meta = entry.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
        name = srv.get("name", "")
        if not name:
            continue
        if name not in unique or meta.get("isLatest"):
            unique[name] = {"server": srv, "meta": meta}

    print(f"Unique servers: {len(unique)}")
    return unique


def save_servers(unique):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for name, data in unique.items():
        srv = data["server"]
        meta = data["meta"]
        agent_id = f"mcp-registry-{name.lower().replace('/', '-').replace(' ', '-')}"
        desc = srv.get("description", "")
        repo = srv.get("repository", {})
        repo_url = repo.get("url", "")
        website = srv.get("websiteUrl", "")
        remotes = srv.get("remotes", [])
        version = srv.get("version", "")

        try:
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 creator_address, agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'mcp_registry', ?, ?, 'mcp', ?, 'mcp_server', ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    description=excluded.description,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                agent_id,
                name,
                desc[:2000],
                repo_url or website,
                json.dumps({
                    "repository": repo,
                    "website": website,
                    "version": version,
                    "remotes": remotes,
                    "icons": srv.get("icons", []),
                    "published_at": meta.get("publishedAt"),
                    "updated_at": meta.get("updatedAt"),
                    "status": meta.get("status"),
                    "schema": srv.get("$schema"),
                }),
                now, now
            ))
            saved += 1
        except Exception as e:
            print(f"  Error saving {name}: {e}")
    conn.commit()
    conn.close()
    return saved


def run():
    print("=== Official MCP Registry Crawler ===")
    unique = fetch_servers()
    saved = save_servers(unique)
    print(f"Saved: {saved} servers")

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='mcp_registry'").fetchone()[0]
    conn.close()
    print(f"MCP Registry total in DB: {total}")


if __name__ == "__main__":
    run()
