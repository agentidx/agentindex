"""
PulseMCP Crawler — fetches MCP servers from api.pulsemcp.com
Source: https://api.pulsemcp.com/v0beta/servers
Stores into agent_crypto_profile table (source='pulsemcp').
"""
import requests, sqlite3, json, time
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
API_URL = "https://api.pulsemcp.com/v0beta/servers"


def fetch_servers():
    all_servers = []
    url = API_URL
    while url:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        batch = data.get("servers", [])
        all_servers.extend(batch)
        total_count = data.get("total_count", len(all_servers))
        url = data.get("next")
        print(f"  Fetched {len(all_servers)}/{total_count} servers...")
        time.sleep(0.3)
    print(f"Fetched {len(all_servers)} servers from PulseMCP (total_count: {total_count})")
    return all_servers


def save_servers(servers):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for s in servers:
        name = s.get("name", "").strip()
        if not name:
            continue
        agent_id = f"pulsemcp-{name.lower().replace(' ', '-')}"
        desc = s.get("short_description") or s.get("EXPERIMENTAL_ai_generated_description") or ""
        source_url = s.get("source_code_url") or s.get("external_url") or s.get("url") or ""
        stars = s.get("github_stars") or 0
        pkg_registry = s.get("package_registry") or ""
        pkg_name = s.get("package_name") or ""
        downloads = s.get("package_download_count") or 0

        try:
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 creator_address, agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'pulsemcp', ?, ?, 'mcp', ?, 'mcp_server', ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    description=excluded.description,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                agent_id,
                name,
                desc[:2000],
                source_url,
                json.dumps({
                    "url": s.get("url"),
                    "external_url": s.get("external_url"),
                    "source_code_url": source_url,
                    "github_stars": stars,
                    "package_registry": pkg_registry,
                    "package_name": pkg_name,
                    "package_download_count": downloads,
                    "remotes": s.get("remotes", []),
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
    print("=== PulseMCP Crawler ===")
    servers = fetch_servers()
    saved = save_servers(servers)
    print(f"Saved: {saved} servers")

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='pulsemcp'").fetchone()[0]
    conn.close()
    print(f"PulseMCP total in DB: {total}")


if __name__ == "__main__":
    run()
