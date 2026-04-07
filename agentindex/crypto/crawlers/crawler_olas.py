import requests, sqlite3, json
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
SUBGRAPH = "https://subgraph.autonolas.tech/subgraphs/name/autonolas"

def fetch_all_units():
    all_units = []
    skip = 0
    while True:
        query = f"""
        {{
          units(first: 100, skip: {skip}, orderBy: tokenId, orderDirection: asc) {{
            id tokenId publicId packageType packageHash
            description metadataHash owner {{ id }} block txHash
          }}
        }}
        """
        r = requests.post(SUBGRAPH, json={"query": query}, timeout=15)
        items = r.json().get("data", {}).get("units", [])
        if not items:
            break
        all_units.extend(items)
        skip += 100
        if len(items) < 100:
            break
    return all_units

def save_units(units):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for u in units:
        try:
            # owner är ett dict {"id": "0x..."} från GraphQL
            owner = u.get("owner")
            if isinstance(owner, dict):
                owner_addr = owner.get("id", "")
            else:
                owner_addr = str(owner) if owner else ""

            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 creator_address, agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'olas', ?, ?, 'ethereum', ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                f"olas-{u['id']}",
                u.get("publicId", ""),
                u.get("description", ""),
                owner_addr,
                u.get("packageType", "service"),
                json.dumps(u),
                now, now
            ))
            saved += 1
        except Exception as e:
            print(f"  DB-fel: {e} | data: {str(u)[:100]}")
    conn.commit()
    conn.close()
    return saved

def run():
    print("=== Olas Crawler ===")
    units = fetch_all_units()
    print(f"Hämtade: {len(units)} units")
    saved = save_units(units)
    print(f"Sparat: {saved} i DB")

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT agent_type, COUNT(*) as c
        FROM agent_crypto_profile
        WHERE source='olas'
        GROUP BY agent_type
    """).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='olas'").fetchone()[0]
    conn.close()
    print(f"Olas totalt i DB: {total}")
    for row in rows:
        print(f"  {row[0]}: {row[1]}")

if __name__ == "__main__":
    run()
