"""
Comparison Generator (BUILD 15)
================================
Generates massive comparison pair lists for /compare/ pages.

Strategy:
- Priority queue (FU-CITATION-20260422-06): top-decile /compare/X-vs-Y
  pairs by measured activation ratio, produced by
  smedjan.measurement.compare_activation_refresh.
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
PRIORITY_QUEUE_FILE = DATA_DIR / "compare_priority_queue.json"

# Score floor reserved for measured-activation pairs; guarantees they sort
# above the stars-based priority used for intra/cross-category pairs
# (star counts in entity_lookup are bounded well below 10^9).
PRIORITY_ACTIVATED_BASE = 1_000_000_000


def _to_slug(name: str) -> str:
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _load_priority_queue() -> list[dict]:
    """Load the smedjan-produced priority queue, or return [] if absent.

    The queue is a JSON file written by
    ``smedjan.measurement.compare_activation_refresh`` containing the
    top-decile /compare/ pairs by measured activation. Absent file ⇒ fall
    back to the legacy pure-permutation strategy.
    """
    if not PRIORITY_QUEUE_FILE.exists():
        logger.info("priority queue not present at %s — skipping", PRIORITY_QUEUE_FILE)
        return []
    try:
        payload = json.loads(PRIORITY_QUEUE_FILE.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning("priority queue unreadable (%s); skipping", exc)
        return []
    pairs = payload.get("pairs") or []
    logger.info(
        "priority queue: %d pairs (snapshot_at=%s)",
        len(pairs), payload.get("snapshot_at"),
    )
    return pairs


def _lookup_names_for_slugs(session, slugs: list[str]) -> dict[str, tuple[str, str | None]]:
    """Map slug → (display_name, category) from entity_lookup. Slugs not
    found return None and are filled in by the caller with the slug itself.
    """
    if not slugs:
        return {}
    rows = session.execute(
        text(
            """
            SELECT slug, name, category
              FROM entity_lookup
             WHERE slug = ANY(:slugs) AND is_active = true
            """
        ),
        {"slugs": slugs},
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def generate_pairs() -> list[dict]:
    """Generate all comparison pairs."""
    priority_pairs_raw = _load_priority_queue()
    with get_db_session() as session:
        # 0. Priority queue — measured activation, already in URL-slug form.
        all_pairs: list[dict] = []
        seen: set[str] = set()

        if priority_pairs_raw:
            slug_set: list[str] = []
            for p in priority_pairs_raw:
                if p.get("slug_a"):
                    slug_set.append(p["slug_a"])
                if p.get("slug_b"):
                    slug_set.append(p["slug_b"])
            name_map = _lookup_names_for_slugs(session, slug_set)

            for p in priority_pairs_raw:
                sa_raw = p.get("slug_a") or ""
                sb_raw = p.get("slug_b") or ""
                if not sa_raw or not sb_raw:
                    continue
                sa, sb = sorted([sa_raw, sb_raw])
                key = f"{sa}-vs-{sb}"
                if key in seen or sa == sb:
                    continue
                seen.add(key)
                a_name, a_cat = name_map.get(sa, (sa, None))
                b_name, b_cat = name_map.get(sb, (sb, None))
                category = a_cat or b_cat or "priority-activated"
                all_pairs.append({
                    "slug": key,
                    "a_name": a_name,
                    "b_name": b_name,
                    "category": category,
                    "type": "priority-activated",
                    "priority": PRIORITY_ACTIVATED_BASE - int(p.get("activation_rank") or 0),
                    "activation_score": p.get("activation_score"),
                    "ai_mediated_7d": p.get("ai_mediated_7d"),
                    "bot_7d": p.get("bot_7d"),
                })

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

    priority = sum(1 for p in pairs if p["type"] == "priority-activated")
    intra = sum(1 for p in pairs if p["type"] == "intra-category")
    cross = sum(1 for p in pairs if p["type"] == "cross-category")
    logger.info(f"  Priority-activated: {priority}")
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
