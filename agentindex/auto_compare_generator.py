#!/usr/bin/env python3
"""
Auto-Generate Comparison Pages (B3)
=====================================
Runs Mondays at 05:00 via LaunchAgent com.nerq.auto-compare.
Looks at recent traffic to /safe/ and /token/ pages, identifies popular
pairs that don't have comparison pages, and generates new ones.

Usage:
    python auto_compare_generator.py              # Dry run (default)
    python auto_compare_generator.py --commit     # Actually add comparisons

Exit 0 on success.
"""

import argparse
import itertools
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LOG_PATH = "/tmp/auto-compare.log"
SCRIPT_DIR = Path(__file__).parent
ANALYTICS_DB = str(Path(__file__).resolve().parent.parent / "logs" / "analytics.db")

# Agent comparison pairs
AGENT_PAIRS_PATH = SCRIPT_DIR / "comparison_pairs.json"
# Token (ZARQ) comparison pairs
TOKEN_PAIRS_PATH = SCRIPT_DIR / "crypto" / "vitality_compare_pairs.json"
# Slug files for category lookup
AGENT_SLUGS_PATH = SCRIPT_DIR / "agent_safety_slugs.json"
TOKEN_SLUGS_PATH = SCRIPT_DIR / "crypto" / "token_slugs.json"

MAX_NEW_PER_RUN = 20
LOOKBACK_DAYS = 7

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("auto-compare")


def get_popular_pages(prefix: str, limit: int = 50) -> list[tuple[str, int]]:
    """Get most-visited pages with given prefix from analytics DB in last 7 days."""
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).isoformat()
        rows = conn.execute("""
            SELECT path, COUNT(*) as hits
            FROM requests
            WHERE path LIKE ?
              AND is_bot = 0
              AND ts >= ?
              AND status = 200
            GROUP BY path
            ORDER BY hits DESC
            LIMIT ?
        """, (f"{prefix}%", cutoff, limit)).fetchall()
        conn.close()
        return [(r[0], r[1]) for r in rows]
    except Exception as e:
        logger.warning("Analytics query failed: %s", e)
        return []


def extract_slug_from_path(path: str, prefix: str) -> str:
    """Extract slug from a path like /safe/foo-bar or /token/bitcoin."""
    return path[len(prefix):].strip("/")


def load_agent_slugs() -> dict:
    """Load agent safety slugs as {slug: info}."""
    if not AGENT_SLUGS_PATH.exists():
        return {}
    with open(AGENT_SLUGS_PATH) as f:
        data = json.load(f)
    return {a["slug"]: a for a in data}


def load_token_slugs() -> dict:
    """Load token slugs as {slug: info}."""
    if not TOKEN_SLUGS_PATH.exists():
        return {}
    with open(TOKEN_SLUGS_PATH) as f:
        return json.load(f)


def load_existing_pairs(path: Path) -> set[str]:
    """Load existing comparison pairs as a set of canonical slugs."""
    if not path.exists():
        return set()
    with open(path) as f:
        data = json.load(f)
    slugs = set()
    for p in data:
        slug = p.get("slug", "")
        if slug:
            slugs.add(slug)
        # Also add reversed form
        parts = slug.split("-vs-")
        if len(parts) == 2:
            slugs.add(f"{parts[1]}-vs-{parts[0]}")
    return slugs


def generate_agent_comparisons(dry_run: bool) -> list[dict]:
    """Generate new agent comparison pairs from popular /safe/ pages."""
    popular = get_popular_pages("/safe/", limit=50)
    if not popular:
        logger.info("No popular /safe/ pages found")
        return []

    slugs_info = load_agent_slugs()
    existing = load_existing_pairs(AGENT_PAIRS_PATH)

    # Get top slugs that actually exist in our slug map
    top_slugs = []
    for path, hits in popular:
        slug = extract_slug_from_path(path, "/safe/")
        if slug and slug in slugs_info:
            top_slugs.append((slug, hits))

    logger.info("Popular agent slugs (with pages): %d", len(top_slugs))

    # Generate pairs from top agents
    new_pairs = []
    seen = set()

    for (a, _), (b, _) in itertools.combinations(top_slugs[:30], 2):
        if a == b:
            continue
        slug = f"{a}-vs-{b}"
        slug_rev = f"{b}-vs-{a}"

        if slug in existing or slug_rev in existing or slug in seen or slug_rev in seen:
            continue

        # Same category preferred
        cat_a = slugs_info.get(a, {}).get("category", "general")
        cat_b = slugs_info.get(b, {}).get("category", "general")

        # Prioritize same-category comparisons
        priority = 1 if cat_a == cat_b else 2

        info_a = slugs_info.get(a, {})
        info_b = slugs_info.get(b, {})

        new_pairs.append({
            "slug": slug,
            "agent_a": info_a.get("name", a),
            "agent_b": info_b.get("name", b),
            "category": cat_a if cat_a == cat_b else "general",
            "priority": priority,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        seen.add(slug)
        seen.add(slug_rev)

    # Sort by priority (same category first), limit
    new_pairs.sort(key=lambda p: p["priority"])
    new_pairs = new_pairs[:MAX_NEW_PER_RUN // 2]  # Split budget between agents and tokens

    if new_pairs and not dry_run:
        with open(AGENT_PAIRS_PATH) as f:
            current = json.load(f)
        # Remove priority field before saving
        for p in new_pairs:
            p.pop("priority", None)
        current.extend(new_pairs)
        with open(AGENT_PAIRS_PATH, "w") as f:
            json.dump(current, f, indent=2)

    return new_pairs


def generate_token_comparisons(dry_run: bool) -> list[dict]:
    """Generate new token comparison pairs from popular /token/ pages."""
    popular = get_popular_pages("/token/", limit=50)
    if not popular:
        logger.info("No popular /token/ pages found")
        return []

    token_slugs = load_token_slugs()
    existing = load_existing_pairs(TOKEN_PAIRS_PATH)

    top_slugs = []
    for path, hits in popular:
        slug = extract_slug_from_path(path, "/token/")
        if slug and slug in token_slugs:
            top_slugs.append((slug, hits))

    logger.info("Popular token slugs (with pages): %d", len(top_slugs))

    # Also include top tokens by importance even if not in traffic
    # This ensures we have meaningful comparisons
    important_tokens = ["bitcoin", "ethereum", "solana", "cardano", "polkadot",
                        "avalanche-2", "arbitrum", "optimism", "sui", "near"]
    for t in important_tokens:
        if t in token_slugs and t not in [s for s, _ in top_slugs]:
            top_slugs.append((t, 0))

    new_pairs = []
    seen = set()

    for (a, _), (b, _) in itertools.combinations(top_slugs[:25], 2):
        if a == b:
            continue
        slug = f"{a}-vs-{b}"
        slug_rev = f"{b}-vs-{a}"

        if slug in existing or slug_rev in existing or slug in seen or slug_rev in seen:
            continue

        info_a = token_slugs.get(a, {})
        info_b = token_slugs.get(b, {})

        new_pairs.append({
            "slug": slug,
            "token_a": a,
            "token_b": b,
            "name_a": info_a.get("name") or a,
            "name_b": info_b.get("name") or b,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        seen.add(slug)
        seen.add(slug_rev)

    new_pairs = new_pairs[:MAX_NEW_PER_RUN // 2]

    if new_pairs and not dry_run:
        with open(TOKEN_PAIRS_PATH) as f:
            current = json.load(f)
        current.extend(new_pairs)
        with open(TOKEN_PAIRS_PATH, "w") as f:
            json.dump(current, f, indent=2)

    return new_pairs


def main():
    parser = argparse.ArgumentParser(description="Auto-generate comparison pages from traffic data")
    parser.add_argument("--commit", action="store_true", help="Actually add comparisons (default: dry run)")
    args = parser.parse_args()

    t0 = time.time()
    now = datetime.now(timezone.utc)
    is_dry_run = not args.commit

    logger.info("=" * 60)
    logger.info("Auto Compare Generator started at %s (%s)", now.isoformat(),
                "DRY RUN" if is_dry_run else "COMMIT")

    # Generate agent comparisons
    agent_pairs = generate_agent_comparisons(is_dry_run)
    logger.info("New agent comparisons: %d", len(agent_pairs))

    # Generate token comparisons
    token_pairs = generate_token_comparisons(is_dry_run)
    logger.info("New token comparisons: %d", len(token_pairs))

    total = len(agent_pairs) + len(token_pairs)

    if is_dry_run and (agent_pairs or token_pairs):
        print(f"\n{'='*72}")
        print(f"[DRY RUN] Would generate {total} new comparison pages")
        print(f"{'='*72}")
        if agent_pairs:
            print("\nAgent Comparisons:")
            for p in agent_pairs:
                print(f"  /compare/{p['slug']}  ({p.get('category', '?')})")
        if token_pairs:
            print("\nToken Comparisons:")
            for p in token_pairs:
                print(f"  /compare/{p['slug']}")
        print(f"{'='*72}")
        print(f"Re-run with --commit to add these.")

    elapsed = time.time() - t0
    logger.info("-" * 60)
    logger.info("AUTO COMPARE COMPLETE")
    logger.info("  Agent comparisons: %d", len(agent_pairs))
    logger.info("  Token comparisons: %d", len(token_pairs))
    logger.info("  Total new:         %d", total)
    logger.info("  Mode:              %s", "dry-run" if is_dry_run else "committed")
    logger.info("  Elapsed:           %.1fs", elapsed)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
