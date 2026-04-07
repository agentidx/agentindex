"""
Comparison Generator (BUILD 15)
================================
Generates massive comparison pair lists for /compare/ pages.

Strategy:
- Top 30 tools per category → all intra-category pairs (435 per category)
- Top 50 tools globally → all cross-category pairs (1,225)
- Total: 5,000-15,000 high-value comparison URLs

Usage:
    python -m agentindex.intelligence.comparison_generator

LaunchAgent: com.nerq.comparison-generator — Daily 05:00
"""

import json
import logging
import sys
from pathlib import Path

from sqlalchemy.sql import text

from agentindex.db.models import get_db_session

logger = logging.getLogger("nerq.comparison_gen")

DATA_DIR = Path(__file__).parent.parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "comparison_pairs.json"


def _to_slug(name: str) -> str:
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def generate_pairs() -> list[dict]:
    """Generate all comparison pairs."""
    with get_db_session() as session:
        # Get all categories with at least 2 scored tools
        cats = session.execute(text("""
            SELECT LOWER(category) as cat, COUNT(*) as cnt
            FROM entity_lookup
            WHERE is_active = true AND trust_score_v2 IS NOT NULL
              AND category IS NOT NULL AND category != ''
            GROUP BY LOWER(category)
            HAVING COUNT(*) >= 2
            ORDER BY cnt DESC
            LIMIT 50
        """)).fetchall()

        all_pairs = []
        seen = set()
        category_tools = {}

        # 1. Intra-category pairs: top 30 tools per category
        for cat_name, cat_count in cats:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, category
                FROM entity_lookup
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND LOWER(category) = :cat
                ORDER BY COALESCE(stars, 0) DESC
                LIMIT 30
            """), {"cat": cat_name}).fetchall()

            tools = [{"name": r[0], "score": r[1], "grade": r[2], "stars": r[3], "category": r[4]} for r in rows]
            category_tools[cat_name] = tools

            for i in range(len(tools)):
                for j in range(i + 1, len(tools)):
                    sa, sb = sorted([_to_slug(tools[i]["name"]), _to_slug(tools[j]["name"])])
                    key = f"{sa}-vs-{sb}"
                    if key not in seen and sa != sb:
                        seen.add(key)
                        all_pairs.append({
                            "slug": key,
                            "a_name": tools[i]["name"] if _to_slug(tools[i]["name"]) == sa else tools[j]["name"],
                            "b_name": tools[j]["name"] if _to_slug(tools[j]["name"]) == sb else tools[i]["name"],
                            "category": cat_name,
                            "type": "intra-category",
                            "priority": min(tools[i].get("stars") or 0, tools[j].get("stars") or 0),
                        })

        # 2. Cross-category pairs: top 50 most popular tools globally
        top_global = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, stars, category
            FROM entity_lookup
            WHERE is_active = true AND trust_score_v2 IS NOT NULL
            ORDER BY COALESCE(stars, 0) DESC
            LIMIT 50
        """)).fetchall()

        global_tools = [{"name": r[0], "score": r[1], "grade": r[2], "stars": r[3], "category": r[4]} for r in top_global]

        for i in range(len(global_tools)):
            for j in range(i + 1, len(global_tools)):
                sa, sb = sorted([_to_slug(global_tools[i]["name"]), _to_slug(global_tools[j]["name"])])
                key = f"{sa}-vs-{sb}"
                if key not in seen and sa != sb:
                    seen.add(key)
                    all_pairs.append({
                        "slug": key,
                        "a_name": global_tools[i]["name"] if _to_slug(global_tools[i]["name"]) == sa else global_tools[j]["name"],
                        "b_name": global_tools[j]["name"] if _to_slug(global_tools[j]["name"]) == sb else global_tools[i]["name"],
                        "category": "cross-category",
                        "type": "cross-category",
                        "priority": min(global_tools[i].get("stars") or 0, global_tools[j].get("stars") or 0),
                    })

    # Sort by priority (higher stars = higher priority)
    all_pairs.sort(key=lambda p: p["priority"], reverse=True)
    return all_pairs


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logger.info("Generating comparison pairs...")

    pairs = generate_pairs()
    logger.info(f"Generated {len(pairs)} unique comparison pairs")

    intra = sum(1 for p in pairs if p["type"] == "intra-category")
    cross = sum(1 for p in pairs if p["type"] == "cross-category")
    logger.info(f"  Intra-category: {intra}")
    logger.info(f"  Cross-category: {cross}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(pairs, f)

    logger.info(f"Saved to {OUTPUT_FILE}")

    # Stats by category
    by_cat = {}
    for p in pairs:
        c = p["category"]
        by_cat[c] = by_cat.get(c, 0) + 1
    for c, n in sorted(by_cat.items(), key=lambda x: -x[1])[:15]:
        logger.info(f"  {c}: {n} pairs")

    return 0


if __name__ == "__main__":
    sys.exit(main())
