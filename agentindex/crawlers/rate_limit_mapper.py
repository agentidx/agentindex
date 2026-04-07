"""
Rate Limit Mapper — Wednesdays 03:30
======================================
Parses README files for rate limit mentions and stores structured data.

Usage:
    python -m agentindex.crawlers.rate_limit_mapper
"""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy.sql import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [rate-limit-mapper] %(message)s",
)
logger = logging.getLogger("rate-limit-mapper")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or ""

if not GITHUB_TOKEN:
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GITHUB_TOKEN="):
                GITHUB_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

MAX_AGENTS = 2000
RATE_DELAY = 0.8

# ── Known rate limits (curated) ────────────────────────────────
CURATED_RATE_LIMITS = [
    {"agent": "openai", "limits": [
        {"tier": "free", "rpm": 3, "rpd": 200, "tpm": 40000, "source": "manual"},
        {"tier": "tier-1", "rpm": 500, "rpd": None, "tpm": 200000, "source": "manual"},
        {"tier": "tier-5", "rpm": 10000, "rpd": None, "tpm": 30000000, "source": "manual"},
    ]},
    {"agent": "anthropic", "limits": [
        {"tier": "free", "rpm": 5, "rpd": None, "tpm": 25000, "source": "manual"},
        {"tier": "build-1", "rpm": 50, "rpd": None, "tpm": 50000, "source": "manual"},
        {"tier": "build-4", "rpm": 4000, "rpd": None, "tpm": 400000, "source": "manual"},
    ]},
    {"agent": "google-gemini", "limits": [
        {"tier": "free", "rpm": 15, "rpd": 1500, "tpm": 1000000, "source": "manual"},
        {"tier": "pro", "rpm": 360, "rpd": None, "tpm": 4000000, "source": "manual"},
    ]},
    {"agent": "groq", "limits": [
        {"tier": "free", "rpm": 30, "rpd": 14400, "tpm": 15000, "source": "manual"},
        {"tier": "paid", "rpm": 30, "rpd": 14400, "tpm": 15000, "source": "manual"},
    ]},
    {"agent": "mistral", "limits": [
        {"tier": "free", "rpm": 1, "rpd": None, "tpm": 500000, "source": "manual"},
        {"tier": "pro", "rpm": 5, "rpd": None, "tpm": 2000000, "source": "manual"},
    ]},
    {"agent": "together-ai", "limits": [
        {"tier": "free", "rpm": 60, "rpd": None, "tpm": None, "source": "manual"},
    ]},
    {"agent": "fireworks-ai", "limits": [
        {"tier": "free", "rpm": 10, "rpd": 500, "tpm": None, "source": "manual"},
        {"tier": "paid", "rpm": 600, "rpd": None, "tpm": None, "source": "manual"},
    ]},
    {"agent": "cohere", "limits": [
        {"tier": "free", "rpm": 20, "rpd": 1000, "tpm": None, "source": "manual"},
        {"tier": "production", "rpm": 10000, "rpd": None, "tpm": None, "source": "manual"},
    ]},
    {"agent": "perplexity", "limits": [
        {"tier": "free", "rpm": 5, "rpd": None, "tpm": None, "source": "manual"},
        {"tier": "pro", "rpm": 50, "rpd": None, "tpm": None, "source": "manual"},
    ]},
    {"agent": "tavily", "limits": [
        {"tier": "free", "rpm": 10, "rpd": 1000, "tpm": None, "source": "manual"},
        {"tier": "paid", "rpm": 100, "rpd": None, "tpm": None, "source": "manual"},
    ]},
    {"agent": "serper", "limits": [
        {"tier": "free", "rpm": 100, "rpd": 2500, "tpm": None, "source": "manual"},
    ]},
    {"agent": "exa-ai", "limits": [
        {"tier": "free", "rpm": 10, "rpd": 1000, "tpm": None, "source": "manual"},
    ]},
    {"agent": "replicate", "limits": [
        {"tier": "free", "rpm": 10, "rpd": None, "tpm": None, "source": "manual"},
        {"tier": "paid", "rpm": 600, "rpd": None, "tpm": None, "source": "manual"},
    ]},
]

# Regex patterns for detecting rate limits in text
RATE_LIMIT_PATTERNS = [
    (r'(\d[\d,]*)\s*(?:requests?|calls?|queries?)\s*(?:per|/)\s*(?:minute|min)', 'rpm'),
    (r'(\d[\d,]*)\s*(?:requests?|calls?|queries?)\s*(?:per|/)\s*(?:hour|hr)', 'rph'),
    (r'(\d[\d,]*)\s*(?:requests?|calls?|queries?)\s*(?:per|/)\s*(?:day)', 'rpd'),
    (r'(\d[\d,]*)\s*(?:RPM|rpm)', 'rpm'),
    (r'(\d[\d,]*)\s*(?:RPH|rph)', 'rph'),
    (r'(\d[\d,]*)\s*(?:RPD|rpd)', 'rpd'),
    (r'(\d[\d,]*)\s*(?:tokens?)\s*(?:per|/)\s*(?:minute|min)', 'tpm'),
    (r'(\d[\d,]*)\s*(?:TPM|tpm)', 'tpm'),
    (r'rate[\s_-]*limit[:\s]*(\d[\d,]*)\s*(?:per|/)\s*(?:minute|min)', 'rpm'),
    (r'rate[\s_-]*limit[:\s]*(\d[\d,]*)\s*(?:per|/)\s*(?:hour|hr)', 'rph'),
    (r'rate[\s_-]*limit[:\s]*(\d[\d,]*)\s*(?:per|/)\s*(?:day)', 'rpd'),
    (r'concurrent[\s_-]*(?:connections?|requests?|limit)[:\s]*(\d+)', 'concurrent'),
]


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            tier TEXT DEFAULT 'default',
            requests_per_minute INTEGER,
            requests_per_hour INTEGER,
            requests_per_day INTEGER,
            tokens_per_minute INTEGER,
            concurrent_limit INTEGER,
            source TEXT DEFAULT 'readme',
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_arl_name ON agent_rate_limits(agent_name)")
    conn.commit()
    conn.close()


def _parse_github_url(url):
    if not url:
        return None
    m = re.search(r'github\.com/([^/]+/[^/]+)', url)
    if m:
        repo = m.group(1).rstrip("/").split("#")[0].split("?")[0]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return repo
    return None


def _fetch_readme(client, repo):
    """Fetch README from GitHub API."""
    url = f"https://api.github.com/repos/{repo}/readme"
    headers = {"Accept": "application/vnd.github.v3.raw"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    try:
        resp = client.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def _extract_rate_limits(text_content):
    """Extract rate limit info from text using regex patterns."""
    results = {}
    for pattern, key in RATE_LIMIT_PATTERNS:
        matches = re.findall(pattern, text_content, re.IGNORECASE)
        if matches:
            # Take the first match, parse number
            val = matches[0].replace(",", "")
            try:
                results[key] = int(val)
            except ValueError:
                pass
    return results


def _store_curated(conn):
    """Store curated rate limits."""
    now = datetime.now().isoformat()
    count = 0

    for entry in CURATED_RATE_LIMITS:
        agent = entry["agent"]
        conn.execute("DELETE FROM agent_rate_limits WHERE agent_name = ?", (agent,))

        for lim in entry["limits"]:
            conn.execute(
                "INSERT INTO agent_rate_limits (agent_name, tier, requests_per_minute, "
                "requests_per_hour, requests_per_day, tokens_per_minute, source, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (agent, lim["tier"], lim.get("rpm"), None,
                 lim.get("rpd"), lim.get("tpm"), lim["source"], now)
            )
            count += 1

    conn.commit()
    return count


def _scan_readme_rate_limits(conn):
    """Scan GitHub READMEs for rate limit info."""
    from agentindex.db.models import get_session
    session = get_session()
    now = datetime.now().isoformat()

    try:
        rows = session.execute(text("""
            SELECT name, source_url
            FROM entity_lookup
            WHERE is_active = true
              AND source_url IS NOT NULL
              AND source_url LIKE '%github.com%'
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
            LIMIT :lim
        """), {"lim": MAX_AGENTS}).fetchall()
    finally:
        session.close()

    logger.info(f"  Scanning {len(rows)} agent READMEs for rate limits...")

    # Skip agents we already have curated data for
    existing = set(
        r[0] for r in conn.execute("SELECT DISTINCT agent_name FROM agent_rate_limits").fetchall()
    )

    found_count = 0
    scanned = 0

    with httpx.Client(timeout=20) as client:
        for row in rows:
            d = dict(row._mapping)
            name = d["name"]

            if name in existing:
                continue

            # Check if recently scanned
            recent = conn.execute(
                "SELECT COUNT(*) FROM agent_rate_limits WHERE agent_name = ? AND fetched_at > datetime('now', '-7 days')",
                (name,)
            ).fetchone()
            if recent and recent[0] > 0:
                continue

            repo = _parse_github_url(d.get("source_url"))
            if not repo:
                continue

            readme = _fetch_readme(client, repo)
            if not readme:
                time.sleep(RATE_DELAY)
                scanned += 1
                continue

            limits = _extract_rate_limits(readme[:20000])
            if limits:
                rpm = limits.get("rpm")
                rph = limits.get("rph")
                rpd = limits.get("rpd")
                tpm = limits.get("tpm")
                concurrent = limits.get("concurrent")

                conn.execute(
                    "INSERT INTO agent_rate_limits (agent_name, tier, requests_per_minute, "
                    "requests_per_hour, requests_per_day, tokens_per_minute, concurrent_limit, source, fetched_at) "
                    "VALUES (?, 'default', ?, ?, ?, ?, ?, 'readme', ?)",
                    (name, rpm, rph, rpd, tpm, concurrent, now)
                )
                found_count += 1

            time.sleep(RATE_DELAY)
            scanned += 1

            if scanned % 100 == 0:
                conn.commit()
                logger.info(f"  Progress: {scanned} scanned, {found_count} rate limits found")

    conn.commit()
    return scanned, found_count


def main():
    logger.info("=" * 60)
    logger.info("Rate Limit Mapper — starting")
    logger.info("=" * 60)

    _init_db()
    conn = sqlite3.connect(str(SQLITE_DB))

    # Step 1: Store curated rate limits
    curated = _store_curated(conn)
    logger.info(f"  Curated rate limit entries: {curated}")

    # Step 2: Scan READMEs
    if GITHUB_TOKEN:
        scanned, found = _scan_readme_rate_limits(conn)
        logger.info(f"  READMEs scanned: {scanned}")
        logger.info(f"  Rate limits detected from READMEs: {found}")
    else:
        logger.warning("  No GITHUB_TOKEN — skipping README scanning")

    # Summary
    total = conn.execute("SELECT COUNT(*) FROM agent_rate_limits").fetchone()[0]
    agents = conn.execute("SELECT COUNT(DISTINCT agent_name) FROM agent_rate_limits").fetchone()[0]

    tiers = conn.execute(
        "SELECT tier, COUNT(*) FROM agent_rate_limits GROUP BY tier ORDER BY COUNT(*) DESC"
    ).fetchall()

    sources = conn.execute(
        "SELECT source, COUNT(*) FROM agent_rate_limits GROUP BY source ORDER BY COUNT(*) DESC"
    ).fetchall()

    conn.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Rate Limit Mapper — COMPLETE")
    logger.info(f"  Total rate limit entries: {total}")
    logger.info(f"  Agents with rate limits: {agents}")
    logger.info(f"  Tier distribution:")
    for tier, count in tiers:
        logger.info(f"    {tier}: {count}")
    logger.info(f"  Source distribution:")
    for source, count in sources:
        logger.info(f"    {source}: {count}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
