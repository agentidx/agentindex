"""
Auto Comparison Generator — Mondays 07:00
==========================================
Generates blog-style comparison posts for top agent pairs.
10 comparisons per run.

Usage:
    python -m agentindex.intelligence.auto_comparisons
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [auto-compare] %(message)s")
logger = logging.getLogger("auto-compare")

from agentindex.db.models import get_session

SQLITE_DB = "/Users/anstudio/agentindex/data/crypto_trust.db"
MAX_POSTS = 10


def _get_top_pairs():
    """Find top agent pairs in same categories for comparison."""
    s = get_session()
    try:
        # Get top agents by category
        rows = s.execute(text("""
            SELECT name, category, COALESCE(trust_score_v2, trust_score) as ts,
                   trust_grade, stars, source, description, compliance_score,
                   source_url, author
            FROM entity_lookup
            WHERE is_active = true
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
              AND stars > 50
              AND category IS NOT NULL
            ORDER BY stars DESC
            LIMIT 200
        """)).fetchall()
    finally:
        s.close()

    # Group by category
    by_cat = {}
    for r in rows:
        d = dict(r._mapping)
        cat = d["category"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(d)

    # Generate pairs from each category (top 2 per category)
    pairs = []
    for cat, agents in by_cat.items():
        if len(agents) >= 2:
            pairs.append((agents[0], agents[1]))
        if len(pairs) >= MAX_POSTS * 2:
            break

    return pairs[:MAX_POSTS]


def _generate_comparison(a: dict, b: dict) -> dict:
    """Generate a comparison blog post."""
    name_a = a["name"]
    name_b = b["name"]
    slug_a = name_a.lower().replace("/", "").replace(" ", "-")
    slug_b = name_b.lower().replace("/", "").replace(" ", "-")
    slug = f"{slug_a}-vs-{slug_b}"
    score_a = float(a["ts"]) if a["ts"] else 0
    score_b = float(b["ts"]) if b["ts"] else 0
    grade_a = a["trust_grade"] or "?"
    grade_b = b["trust_grade"] or "?"
    stars_a = a.get("stars", 0) or 0
    stars_b = b.get("stars", 0) or 0
    comp_a = float(a.get("compliance_score") or 0)
    comp_b = float(b.get("compliance_score") or 0)
    cat = a["category"]

    winner = name_a if score_a >= score_b else name_b
    winner_score = max(score_a, score_b)

    desc_a = (a.get("description") or "")[:200]
    desc_b = (b.get("description") or "")[:200]

    content = f"""# {name_a} vs {name_b}: Trust, Security & Compatibility 2026

Choosing between {name_a} and {name_b}? This independent comparison analyzes both {cat} tools across trust scores, security vulnerabilities, compliance, and community health — all based on Nerq's analysis of 204K+ AI assets.

## Trust Score Comparison

| Metric | {name_a} | {name_b} |
|--------|----------|----------|
| Trust Score | {score_a:.0f}/100 | {score_b:.0f}/100 |
| Grade | {grade_a} | {grade_b} |
| Stars | {stars_a:,} | {stars_b:,} |
| Compliance | {comp_a:.0f}/100 | {comp_b:.0f}/100 |
| Source | {a.get("source", "N/A")} | {b.get("source", "N/A")} |

## Overview

**{name_a}**: {desc_a}

**{name_b}**: {desc_b}

## Verdict

Based on Nerq's independent analysis across 13+ data sources and 52 global AI regulations, **{winner}** scores higher with a trust score of {winner_score:.0f}/100. {"Both are strong choices" if abs(score_a - score_b) < 10 else f"{winner} has a clear advantage"} in the {cat} category.

When choosing between these tools, consider your specific requirements:
- If community size matters most: {"choose " + name_a if stars_a > stars_b else "choose " + name_b} ({max(stars_a, stars_b):,} stars)
- If compliance is critical: {"choose " + name_a if comp_a > comp_b else "choose " + name_b} ({max(comp_a, comp_b):.0f}/100 compliance)
- If overall trust is the priority: choose {winner} ({winner_score:.0f}/100)

Always run `nerq check {name_a.lower().split("/")[-1]}` before integrating any AI tool.

---

*Trust scores by [Nerq](https://nerq.ai). Updated daily. [Check any agent](https://nerq.ai/v1/preflight?target={name_a}).*
"""

    faq = [
        {
            "q": f"Is {name_a} or {name_b} safer?",
            "a": f"According to Nerq's trust analysis, {winner} has a higher trust score ({winner_score:.0f}/100). Both are assessed across 52 global AI regulations."
        },
        {
            "q": f"What is {name_a}'s trust score?",
            "a": f"{name_a} has a Nerq Trust Score of {score_a:.0f}/100 ({grade_a}), with {stars_a:,} stars and a compliance score of {comp_a:.0f}/100."
        },
        {
            "q": f"Which {cat} tool should I use?",
            "a": f"Based on trust scores, {winner} ({winner_score:.0f}/100) is the higher-rated option. Consider your specific needs for security, compliance, and community support."
        },
    ]

    return {
        "slug": slug,
        "title": f"{name_a} vs {name_b}: Trust, Security & Compatibility 2026",
        "content": content,
        "faq": faq,
        "category": cat,
        "agents": [name_a, name_b],
        "winner": winner,
        "generated_at": datetime.utcnow().isoformat(),
    }


def _save_comparison(comp: dict):
    """Save comparison to SQLite for serving."""
    try:
        conn = sqlite3.connect(SQLITE_DB, timeout=10)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_comparisons (
                slug TEXT PRIMARY KEY,
                title TEXT,
                content TEXT,
                faq TEXT,
                category TEXT,
                agents TEXT,
                winner TEXT,
                generated_at TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO auto_comparisons (slug, title, content, faq, category, agents, winner, generated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (comp["slug"], comp["title"], comp["content"], json.dumps(comp["faq"]),
             comp["category"], json.dumps(comp["agents"]), comp["winner"], comp["generated_at"])
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save comparison {comp['slug']}: {e}")
        return False


def run():
    """Generate comparison posts."""
    pairs = _get_top_pairs()
    logger.info(f"Generating {len(pairs)} comparison posts")

    generated = 0
    for a, b in pairs:
        comp = _generate_comparison(a, b)
        if _save_comparison(comp):
            generated += 1
            logger.info(f"  [{generated}] {comp['title']}")

    logger.info(f"Generated {generated} comparison posts")
    return generated


def main():
    logger.info("=" * 60)
    logger.info("Auto Comparison Generator — starting")
    logger.info("=" * 60)
    count = run()
    logger.info(f"Complete: {count} posts generated")


if __name__ == "__main__":
    main()
