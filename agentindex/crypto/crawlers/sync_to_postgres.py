"""
Sync Pipeline: agent_crypto_profile (SQLite staging) → agents (PostgreSQL main)

Only syncs entries where agent_type IN ('agent', 'tool', 'mcp_server', 'model').
Deduplicates by source_url (unique constraint in PostgreSQL).
Applies trust scoring to new entries.

Usage: python3 agentindex/crypto/crawlers/sync_to_postgres.py
"""
import sqlite3
import json
import uuid
import math
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/Users/anstudio/agentindex/.env")

SQLITE_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
VALID_TYPES = ("agent", "tool", "mcp_server", "model")

# Source URL prefix patterns for generating unique URLs
SOURCE_URL_PATTERNS = {
    "pulsemcp": "https://pulsemcp.com/servers/{name}",
    "mcp_registry": "https://registry.modelcontextprotocol.io/servers/{name}",
    "agentverse": "https://agentverse.ai/agents/{name}",
    "openrouter": "https://openrouter.ai/models/{name}",
    "lobehub": "https://lobehub.com/agents/{name}",
    "erc8004": "https://8004scan.io/agents/{name}",
    "fetchai": "https://agentverse.ai/agents/fetchai/{name}",
    "virtuals": "https://app.virtuals.io/agents/{name}",
    "bittensor": "https://bittensor.com/subnets/{name}",
    "olas": "https://registry.olas.network/agents/{name}",
    "coingecko": "https://coingecko.com/tokens/{name}",
    "dexscreener": "https://dexscreener.com/tokens/{name}",
}


def get_pg_connection():
    """Get PostgreSQL connection via psycopg2."""
    from agentindex.db_config import get_write_conn
    return get_write_conn()


def get_existing_source_urls(pg_conn, sources):
    """Get all existing source_urls from PostgreSQL for the given sources."""
    cur = pg_conn.cursor()
    placeholders = ",".join(["%s"] * len(sources))
    cur.execute(f"SELECT source_url FROM entity_lookup WHERE source IN ({placeholders})", sources)
    existing = set(row[0] for row in cur.fetchall())
    cur.close()
    return existing


def generate_source_url(source, agent_id, name, metadata_json):
    """Generate a unique source_url for an entry."""
    meta = {}
    if metadata_json:
        try:
            meta = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
        except (json.JSONDecodeError, TypeError):
            pass

    # Try to use real URL from metadata first
    real_url = meta.get("source_code_url") or meta.get("repository", {}).get("url") or meta.get("website") or meta.get("homepage")
    if real_url and real_url.startswith("http"):
        return real_url

    # Fall back to pattern-based URL
    pattern = SOURCE_URL_PATTERNS.get(source, f"https://nerq.ai/crypto/{source}/{{name}}")
    slug = (name or agent_id or "unknown").lower().replace(" ", "-").replace("/", "-")[:200]
    return pattern.format(name=slug)


def compute_trust_score(row):
    """
    Compute trust_score_v2 for a staging entry.
    Simplified scoring based on available data.
    Returns (score, grade, risk_level, dimensions).
    """
    name = row.get("agent_name", "") or ""
    desc = row.get("description", "") or ""
    source = row.get("source", "")
    agent_type = row.get("agent_type", "")
    meta = {}
    if row.get("metadata_json"):
        try:
            meta = json.loads(row["metadata_json"]) if isinstance(row["metadata_json"], str) else row["metadata_json"]
        except (json.JSONDecodeError, TypeError):
            pass

    scores = {}

    # 1. Documentation (0-100, weight 0.25)
    doc_score = 0
    if desc:
        dlen = len(desc)
        if dlen >= 200:
            doc_score = 80
        elif dlen >= 100:
            doc_score = 65
        elif dlen >= 50:
            doc_score = 50
        elif dlen >= 20:
            doc_score = 35
        else:
            doc_score = 20
    if name and 5 <= len(name) <= 60:
        doc_score += 15
    elif name:
        doc_score += 5
    scores["documentation"] = min(100, doc_score)

    # 2. Source credibility (0-100, weight 0.20)
    source_cred = {
        "mcp_registry": 85, "pulsemcp": 70, "lobehub": 65,
        "openrouter": 75, "agentverse": 60, "erc8004": 55,
        "fetchai": 60, "virtuals": 50, "bittensor": 65,
        "olas": 65, "coingecko": 60, "dexscreener": 50,
    }
    scores["source_credibility"] = source_cred.get(source, 50)

    # 3. Popularity (0-100, weight 0.20)
    pop_score = 30  # base
    stars = meta.get("github_stars") or meta.get("star_count") or 0
    downloads = meta.get("package_download_count") or 0
    interactions = meta.get("total_interactions") or 0

    if stars >= 1000:
        pop_score = 90
    elif stars >= 100:
        pop_score = 75
    elif stars >= 10:
        pop_score = 55
    elif stars >= 1:
        pop_score = 40

    if downloads >= 10000:
        pop_score = max(pop_score, 80)
    elif downloads >= 1000:
        pop_score = max(pop_score, 65)

    if interactions >= 1000:
        pop_score = max(pop_score, 70)
    elif interactions >= 100:
        pop_score = max(pop_score, 55)

    scores["popularity"] = min(100, pop_score)

    # 4. Ecosystem fit (0-100, weight 0.15)
    eco_score = 50
    if agent_type == "mcp_server":
        eco_score = 70  # MCP servers are in-demand
    elif agent_type == "agent":
        eco_score = 60
    elif agent_type == "model":
        eco_score = 65

    # Boost for having protocols/remotes
    if meta.get("remotes"):
        eco_score += 15
    if meta.get("protocols"):
        eco_score += 10
    if meta.get("a2a_endpoint"):
        eco_score += 10
    if meta.get("mcp_server"):
        eco_score += 10
    scores["ecosystem"] = min(100, eco_score)

    # 5. Metadata completeness (0-100, weight 0.10)
    completeness = 30
    if meta.get("repository") or meta.get("source_code_url"):
        completeness += 20
    if meta.get("version"):
        completeness += 15
    if meta.get("category") or meta.get("tags"):
        completeness += 15
    if meta.get("author") or meta.get("homepage"):
        completeness += 10
    if meta.get("license"):
        completeness += 10
    scores["completeness"] = min(100, completeness)

    # 6. Recency (0-100, weight 0.10)
    recency = 60  # default
    created = meta.get("created_at") or meta.get("published_at")
    if created:
        try:
            if isinstance(created, str):
                # Try parsing various date formats
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"]:
                    try:
                        dt = datetime.strptime(created[:26].replace("Z", ""), fmt)
                        days = (datetime.utcnow() - dt).days
                        if days <= 30:
                            recency = 90
                        elif days <= 90:
                            recency = 75
                        elif days <= 365:
                            recency = 60
                        else:
                            recency = 45
                        break
                    except ValueError:
                        continue
        except Exception:
            pass
    scores["recency"] = recency

    # Weighted total
    weights = {
        "documentation": 0.25,
        "source_credibility": 0.20,
        "popularity": 0.20,
        "ecosystem": 0.15,
        "completeness": 0.10,
        "recency": 0.10,
    }
    total = sum(scores[k] * weights[k] for k in weights)
    total = round(total, 1)

    # Grade
    if total >= 90:
        grade = "A+"
    elif total >= 85:
        grade = "A"
    elif total >= 80:
        grade = "A-"
    elif total >= 75:
        grade = "B+"
    elif total >= 70:
        grade = "B"
    elif total >= 65:
        grade = "B-"
    elif total >= 60:
        grade = "C+"
    elif total >= 55:
        grade = "C"
    elif total >= 50:
        grade = "C-"
    elif total >= 45:
        grade = "D+"
    elif total >= 40:
        grade = "D"
    else:
        grade = "F"

    # Risk level
    if total >= 70:
        risk_level = "TRUSTED"
    elif total >= 50:
        risk_level = "CAUTION"
    else:
        risk_level = "UNTRUSTED"

    return total, grade, risk_level, scores


def extract_metadata_fields(row):
    """Extract additional fields from metadata_json."""
    meta = {}
    if row.get("metadata_json"):
        try:
            meta = json.loads(row["metadata_json"]) if isinstance(row["metadata_json"], str) else row["metadata_json"]
        except (json.JSONDecodeError, TypeError):
            pass

    stars = meta.get("github_stars") or meta.get("star_count") or 0
    author = row.get("creator_address") or meta.get("author") or meta.get("owner") or ""
    category = meta.get("category") or ""
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    language = meta.get("language") or ""
    license_str = meta.get("license") or ""
    source_code_url = meta.get("source_code_url") or meta.get("repository", {}).get("url") or ""
    protocols = []
    if meta.get("remotes"):
        protocols.append("mcp")
    if meta.get("a2a_endpoint"):
        protocols.append("a2a")
    if meta.get("x402_supported"):
        protocols.append("x402")

    return {
        "stars": int(stars) if stars else 0,
        "author": str(author)[:255] if author else "",
        "category": str(category)[:100] if category else "",
        "tags": tags[:20] if tags else [],
        "language": str(language)[:50] if language else "",
        "license": str(license_str)[:100] if license_str else "",
        "source_code_url": source_code_url,
        "protocols": protocols,
    }


def sync():
    """Main sync: SQLite staging → PostgreSQL main."""
    print("=== Sync: agent_crypto_profile → PostgreSQL agents ===")

    # 1. Read all valid entries from SQLite
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    type_placeholders = ",".join(f"'{t}'" for t in VALID_TYPES)
    rows = sqlite_conn.execute(f"""
        SELECT * FROM agent_crypto_profile
        WHERE agent_type IN ({type_placeholders})
    """).fetchall()
    print(f"SQLite staging: {len(rows)} valid entries (types: {VALID_TYPES})")

    if not rows:
        print("Nothing to sync.")
        sqlite_conn.close()
        return

    # 2. Get sources we need to check
    sources = list(set(dict(r)["source"] for r in rows))
    print(f"Sources to sync: {sources}")

    # 3. Connect to PostgreSQL and get existing URLs
    pg_conn = get_pg_connection()
    existing_urls = get_existing_source_urls(pg_conn, sources)
    print(f"Existing entries in PG for these sources: {len(existing_urls)}")

    # 4. Process each entry
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    inserted = 0
    skipped_dedup = 0
    skipped_error = 0
    trust_distribution = {"TRUSTED": 0, "CAUTION": 0, "UNTRUSTED": 0}
    score_sum = 0.0

    cur = pg_conn.cursor()
    batch = []

    for r in rows:
        row = dict(r)
        source_url = generate_source_url(row["source"], row["agent_id"], row["agent_name"], row.get("metadata_json"))

        # Deduplicate
        if source_url in existing_urls:
            skipped_dedup += 1
            continue

        # Mark as seen to avoid duplicates within this batch
        existing_urls.add(source_url)

        # Compute trust score
        trust_score, trust_grade, risk_level, dimensions = compute_trust_score(row)
        score_sum += trust_score
        trust_distribution[risk_level] += 1

        # Extract metadata fields
        meta_fields = extract_metadata_fields(row)

        entry = {
            "id": str(uuid.uuid4()),
            "source": row["source"],
            "source_url": source_url,
            "source_id": row["agent_id"],
            "name": (row.get("agent_name") or row["agent_id"] or "unknown")[:500],
            "description": (row.get("description") or "")[:10000],
            "author": meta_fields["author"],
            "license": meta_fields["license"],
            "category": meta_fields["category"],
            "tags": meta_fields["tags"],
            "stars": meta_fields["stars"],
            "language": meta_fields["language"],
            "protocols": meta_fields["protocols"],
            "agent_type": row["agent_type"],
            "is_active": True,
            "is_verified": False,
            "crawl_status": "indexed",
            "first_indexed": now,
            "last_crawled": now,
            "trust_score": trust_score,
            "trust_score_v2": trust_score,
            "trust_grade": trust_grade,
            "trust_risk_level": risk_level,
            "trust_dimensions": json.dumps(dimensions),
            "trust_scored_at": now,
            "raw_metadata": row.get("metadata_json") or "{}",
        }
        batch.append(entry)

        # Insert in batches of 1000
        if len(batch) >= 1000:
            count = _insert_batch(cur, batch)
            inserted += count
            skipped_error += len(batch) - count
            batch = []
            if inserted % 10000 == 0:
                print(f"  Inserted {inserted}...")
                pg_conn.commit()

    # Insert remaining
    if batch:
        count = _insert_batch(cur, batch)
        inserted += count
        skipped_error += len(batch) - count

    pg_conn.commit()
    cur.close()

    # 5. Report
    avg_score = score_sum / (inserted + skipped_dedup) if (inserted + skipped_dedup) > 0 else 0
    print(f"\n=== Sync Results ===")
    print(f"  New entries inserted:  {inserted:>8,}")
    print(f"  Skipped (dedup):       {skipped_dedup:>8,}")
    print(f"  Skipped (error):       {skipped_error:>8,}")
    print(f"  Average trust score:   {avg_score:>8.1f}")
    print(f"  Trust distribution:")
    for level, count in trust_distribution.items():
        print(f"    {level:12s} {count:>8,}")

    # 6. Get new totals
    cur = pg_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM entity_lookup WHERE agent_type IN ('agent','tool','mcp_server')")
    total_atm = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM entity_lookup")
    total_all = cur.fetchone()[0]
    cur.execute("SELECT agent_type, COUNT(*) FROM entity_lookup GROUP BY agent_type ORDER BY COUNT(*) DESC")
    type_counts = cur.fetchall()
    cur.close()
    pg_conn.close()
    sqlite_conn.close()

    print(f"\n=== PostgreSQL Totals ===")
    print(f"  Agents + Tools + MCP:  {total_atm:>10,}")
    print(f"  All entries:           {total_all:>10,}")
    print(f"\n  By type:")
    for t, c in type_counts:
        print(f"    {str(t):15s} {c:>10,}")

    return inserted


def _insert_batch(cur, batch):
    """Insert a batch of entries into PostgreSQL, handling duplicates."""
    inserted = 0
    for entry in batch:
        try:
            cur.execute("""
                INSERT INTO agents (
                    id, source, source_url, source_id, name, description,
                    author, license, category, tags, stars, language,
                    protocols, agent_type, is_active, is_verified, crawl_status,
                    first_indexed, last_crawled,
                    trust_score, trust_score_v2, trust_grade, trust_risk_level,
                    trust_dimensions, trust_scored_at, raw_metadata
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (source_url) DO NOTHING
            """, (
                entry["id"], entry["source"], entry["source_url"], entry["source_id"],
                entry["name"], entry["description"],
                entry["author"], entry["license"], entry["category"],
                entry["tags"] or None, entry["stars"], entry["language"],
                entry["protocols"] or None, entry["agent_type"],
                entry["is_active"], entry["is_verified"], entry["crawl_status"],
                entry["first_indexed"], entry["last_crawled"],
                entry["trust_score"], entry["trust_score_v2"], entry["trust_grade"],
                entry["trust_risk_level"],
                entry["trust_dimensions"], entry["trust_scored_at"],
                entry["raw_metadata"],
            ))
            if cur.rowcount > 0:
                inserted += 1
        except Exception as e:
            # Skip individual errors (e.g., constraint violations)
            cur.connection.rollback()
            pass
    return inserted


if __name__ == "__main__":
    sync()
