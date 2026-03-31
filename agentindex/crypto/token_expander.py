#!/usr/bin/env python3
"""
Token Expander (A1)
====================
Runs weekly on Sundays at 06:00 via LaunchAgent com.zarq.token-expander.
Fetches all protocols from DeFiLlama, identifies tokens NOT already in our
database, and adds new ones to the pipeline tables + token_slugs.json.

Usage:
    python token_expander.py              # Dry run (default)
    python token_expander.py --commit     # Actually add to DB

Exit 0 on success.
"""

import argparse
import json
import logging
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = "/tmp/token-expander.log"
DB_PATH = str(Path(__file__).parent / "crypto_trust.db")
TOKEN_SLUGS_PATH = Path(__file__).parent / "token_slugs.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("token-expander")

DEFILLAMA_PROTOCOLS = "https://api.llama.fi/protocols"
DEFILLAMA_CHAINS = "https://api.llama.fi/v2/chains"


def fetch_json(url: str) -> list | dict | None:
    """Fetch JSON from a URL."""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "ZARQ-TokenExpander/1.0")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.error("Failed to fetch %s: %s", url, e)
        return None


def get_existing_tokens(conn: sqlite3.Connection) -> tuple[set, set]:
    """Get existing token_ids from NDD daily and protocol tokens tables."""
    ndd_ids = set()
    for row in conn.execute("SELECT DISTINCT token_id FROM crypto_ndd_daily"):
        ndd_ids.add(row[0])

    protocol_ids = set()
    for row in conn.execute("SELECT DISTINCT protocol_id FROM defi_protocol_tokens WHERE protocol_id IS NOT NULL"):
        protocol_ids.add(row[0])

    return ndd_ids, protocol_ids


def load_token_slugs() -> dict:
    """Load current token_slugs.json."""
    if TOKEN_SLUGS_PATH.exists():
        try:
            with open(TOKEN_SLUGS_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def determine_tier(tvl: float, chains: list, category: str) -> str:
    """Determine risk tier for a new token based on available data."""
    if tvl and tvl > 100_000_000:
        return "T2"  # Significant TVL, NDD-eligible
    if tvl and tvl > 10_000_000:
        return "T3"
    return "T4"  # Low TVL, basic monitoring


def determine_risk_grade(tvl: float, audit_count: int, chains: list) -> str:
    """Rough risk grade for new tokens."""
    score = 0
    if tvl and tvl > 100_000_000:
        score += 30
    elif tvl and tvl > 10_000_000:
        score += 20
    elif tvl and tvl > 1_000_000:
        score += 10

    if audit_count and audit_count > 0:
        score += 20

    if chains and len(chains) > 3:
        score += 10
    elif chains and len(chains) > 1:
        score += 5

    if score >= 50:
        return "B-"
    if score >= 30:
        return "C+"
    if score >= 15:
        return "C"
    return "C-"


def main():
    parser = argparse.ArgumentParser(description="ZARQ Token Expander — discover new tokens from DeFiLlama")
    parser.add_argument("--commit", action="store_true", help="Actually add to DB (default: dry run)")
    args = parser.parse_args()

    t0 = time.time()
    now = datetime.now(timezone.utc)
    is_dry_run = not args.commit

    logger.info("=" * 60)
    logger.info("Token Expander started at %s (%s)", now.isoformat(), "DRY RUN" if is_dry_run else "COMMIT")

    # Fetch DeFiLlama data
    logger.info("Fetching DeFiLlama protocols...")
    protocols = fetch_json(DEFILLAMA_PROTOCOLS)
    if not protocols:
        logger.error("Failed to fetch protocols")
        return 1
    logger.info("Fetched %d protocols from DeFiLlama", len(protocols))

    logger.info("Fetching DeFiLlama chains...")
    chains_data = fetch_json(DEFILLAMA_CHAINS)
    chain_tvls = {}
    if chains_data:
        for c in chains_data:
            chain_tvls[c.get("name", "")] = c.get("tvl", 0)
        logger.info("Fetched %d chains", len(chain_tvls))

    # Get existing tokens
    conn = sqlite3.connect(DB_PATH)
    existing_ndd, existing_protocol = get_existing_tokens(conn)
    logger.info("Existing: %d NDD tokens, %d protocol IDs", len(existing_ndd), len(existing_protocol))

    # Load current token slugs
    token_slugs = load_token_slugs()
    logger.info("Current token_slugs.json: %d entries", len(token_slugs))

    # Identify new protocols
    new_protocols = []
    for proto in protocols:
        slug = proto.get("slug", "")
        if not slug:
            continue

        # Skip if already in our system
        gecko_id = proto.get("gecko_id")
        if gecko_id and gecko_id in existing_ndd:
            continue
        if slug in existing_protocol:
            continue
        if gecko_id and gecko_id in token_slugs:
            continue

        tvl = proto.get("tvl", 0) or 0
        chains = proto.get("chains", [])
        category = proto.get("category", "")
        audit_count = len(proto.get("audits", []) or [])
        name = proto.get("name", slug)
        symbol = proto.get("symbol", "")

        # Only add protocols with meaningful TVL
        if tvl < 100_000:
            continue

        new_protocols.append({
            "protocol_id": slug,
            "token_id": gecko_id,
            "symbol": symbol,
            "name": name,
            "category": category,
            "chains": json.dumps(chains) if chains else None,
            "audit_count": audit_count,
            "forked_from": proto.get("forkedFrom", ""),
            "listed_at": str(proto.get("listedAt", "")),
            "url": proto.get("url", ""),
            "tvl_latest": tvl,
            "crawled_at": now.isoformat(),
            "tier": determine_tier(tvl, chains, category),
            "risk_grade": determine_risk_grade(tvl, audit_count, chains),
        })

    logger.info("New protocols with TVL >= $100K: %d", len(new_protocols))

    # Sort by TVL descending
    new_protocols.sort(key=lambda p: p["tvl_latest"], reverse=True)

    # Report top finds
    if new_protocols:
        logger.info("Top 20 new protocols by TVL:")
        for p in new_protocols[:20]:
            logger.info("  %-30s TVL=$%.1fM  chains=%s  cat=%s",
                        p["name"][:30], p["tvl_latest"] / 1e6,
                        p["chains"][:50] if p["chains"] else "?",
                        p["category"][:20])

    if is_dry_run:
        logger.info("-" * 60)
        logger.info("DRY RUN — would add %d protocols", len(new_protocols))
        logger.info("Re-run with --commit to actually add to database")
        conn.close()
        elapsed = time.time() - t0
        logger.info("Elapsed: %.1fs", elapsed)
        logger.info("=" * 60)
        return 0

    # COMMIT mode: add to database
    added_protocols = 0
    added_slugs = 0

    for p in new_protocols:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO defi_protocol_tokens
                (protocol_id, token_id, symbol, name, category, chains,
                 audit_count, forked_from, listed_at, url, tvl_latest, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p["protocol_id"], p["token_id"], p["symbol"], p["name"],
                p["category"], p["chains"], p["audit_count"], p["forked_from"],
                p["listed_at"], p["url"], p["tvl_latest"], p["crawled_at"],
            ))
            added_protocols += 1
        except sqlite3.IntegrityError:
            pass

        # Add to token_slugs if we have a gecko_id
        slug_id = p["token_id"] or p["protocol_id"]
        if slug_id and slug_id not in token_slugs:
            token_slugs[slug_id] = {
                "symbol": p["symbol"],
                "name": p["name"],
                "tier": p["tier"],
                "risk_grade": p["risk_grade"],
            }
            added_slugs += 1

    conn.commit()
    conn.close()

    # Save updated token_slugs
    if added_slugs > 0:
        with open(TOKEN_SLUGS_PATH, "w") as f:
            json.dump(token_slugs, f, indent=2)

    elapsed = time.time() - t0
    logger.info("-" * 60)
    logger.info("TOKEN EXPANDER COMPLETE")
    logger.info("  DeFiLlama protocols:  %d", len(protocols))
    logger.info("  New (TVL >= $100K):    %d", len(new_protocols))
    logger.info("  Added to DB:          %d", added_protocols)
    logger.info("  Added to slugs:       %d", added_slugs)
    logger.info("  Total token_slugs:    %d", len(token_slugs))
    logger.info("  Elapsed:              %.1fs", elapsed)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
