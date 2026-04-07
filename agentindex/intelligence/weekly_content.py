"""
Weekly Auto-Content Generator (BUILD 14)
==========================================
Generates weekly blog posts from DB data:
- "New This Week" — newly indexed tools
- "Trust Movers" — biggest score changes
- "Category Spotlight" — rotating deep dive

Usage:
    python -m agentindex.intelligence.weekly_content

LaunchAgent: com.nerq.weekly-content — Mondays 09:00
"""

import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.sql import text

from agentindex.db.models import get_db_session

logger = logging.getLogger("nerq.weekly_content")

DATA_DIR = Path(__file__).parent.parent.parent / "data"
POSTS_DIR = DATA_DIR / "weekly_posts"

CATEGORIES_ROTATION = [
    "coding", "communication", "automation", "security", "data",
    "marketing", "finance", "education", "healthcare", "legal",
    "devops", "testing", "search", "monitoring", "content",
    "database", "api", "browser", "email", "voice",
    "image", "translation", "gaming", "research", "robotics",
    "compliance", "analytics", "infrastructure", "networking", "other",
]


def _to_slug(s: str) -> str:
    import re
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def generate_weekly_posts() -> list[dict]:
    """Generate all weekly posts and return them as dicts."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    date_str = week_start.isoformat()
    posts = []

    with get_db_session() as session:
        # 1. New This Week
        new_tools = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, stars, category, description
            FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
              AND first_indexed > NOW() - INTERVAL '7 days'
            ORDER BY COALESCE(stars, 0) DESC
            LIMIT 20
        """)).fetchall()

        if new_tools:
            items = ""
            for r in new_tools:
                name, score, grade, stars, cat, desc = r
                slug = _to_slug(name)
                items += f"- [{name}](/is-{slug}-safe) — {cat or 'general'}, Trust: {score:.0f}/100"
                if desc:
                    items += f". {desc[:100]}"
                items += "\n"

            posts.append({
                "slug": f"new-this-week-{date_str}",
                "title": f"New AI Tools This Week — {today.strftime('%B %d, %Y')}",
                "tag": "New Arrivals",
                "body_md": f"# New AI Tools This Week\n\n{len(new_tools)} new tools were indexed this week.\n\n{items}\n\n[View all new tools →](/new)",
                "excerpt": f"{len(new_tools)} new AI tools indexed this week with independent trust scores.",
            })

        # 2. Trust Movers — tools with highest score (proxy: top scoring recently crawled)
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        movers = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, stars, category
            FROM agents WHERE is_active = true AND trust_score_v2 IS NOT NULL
              AND last_crawled > NOW() - INTERVAL '7 days'
            ORDER BY trust_score_v2 DESC
            LIMIT 10
        """)).fetchall()

        if movers:
            items = ""
            for r in movers:
                name, score, grade, stars, cat = r
                slug = _to_slug(name)
                items += f"- [{name}](/is-{slug}-safe) — Score: {score:.0f}/100, Grade: {grade or 'N/A'}\n"

            posts.append({
                "slug": f"trust-movers-{date_str}",
                "title": f"Top Trusted AI Tools — Week of {today.strftime('%B %d, %Y')}",
                "tag": "Trust Movers",
                "body_md": f"# Top Trusted AI Tools\n\nHighest-scoring tools updated this week:\n\n{items}\n\n[View full leaderboard →](/leaderboard)",
                "excerpt": "This week's highest-scoring AI tools by Nerq Trust Score.",
            })

        # 3. Category Spotlight
        week_num = today.isocalendar()[1]
        cat_idx = week_num % len(CATEGORIES_ROTATION)
        spotlight_cat = CATEGORIES_ROTATION[cat_idx]

        cat_tools = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, stars, description
            FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
              AND LOWER(category) = :cat
            ORDER BY trust_score_v2 DESC
            LIMIT 15
        """), {"cat": spotlight_cat}).fetchall()

        cat_total = session.execute(text("""
            SELECT COUNT(*) FROM entity_lookup WHERE is_active = true AND LOWER(category) = :cat
        """), {"cat": spotlight_cat}).scalar() or 0

        if cat_tools:
            items = ""
            for i, r in enumerate(cat_tools, 1):
                name, score, grade, stars, desc = r
                slug = _to_slug(name)
                items += f"{i}. [{name}](/is-{slug}-safe) — {score:.0f}/100 ({grade or 'N/A'})\n"

            posts.append({
                "slug": f"spotlight-{spotlight_cat}-{date_str}",
                "title": f"Category Spotlight: {spotlight_cat.title()} Tools — {today.strftime('%B %Y')}",
                "tag": "Spotlight",
                "body_md": f"# {spotlight_cat.title()} Tools Spotlight\n\n{cat_total:,} tools in this category. Top 15 by trust score:\n\n{items}\n\n[Browse all {spotlight_cat} tools →](/best/{spotlight_cat})",
                "excerpt": f"Deep dive into {cat_total:,} {spotlight_cat} tools. Rankings, trust scores, and recommendations.",
            })

    return posts


def save_posts(posts: list[dict]):
    """Save posts to data directory."""
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    for p in posts:
        path = POSTS_DIR / f"{p['slug']}.json"
        with open(path, "w") as f:
            json.dump(p, f, indent=2)
        logger.info(f"Saved: {path.name}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logger.info("Generating weekly content...")

    posts = generate_weekly_posts()
    logger.info(f"Generated {len(posts)} posts")

    save_posts(posts)

    for p in posts:
        logger.info(f"  {p['tag']}: {p['title']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
