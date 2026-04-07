#!/usr/bin/env python3
"""
Add newly detected tools from data/new_tools_detected.json into the PostgreSQL agents table.
Computes trust_score_v2 and trust_grade, generates safety slugs.
"""

import json
import math
import re
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.sql import text

# Reuse project DB session
from agentindex.db.models import get_db_session

DATA_FILE = Path(__file__).parent / "data" / "new_tools_detected.json"
SLUGS_FILE = Path(__file__).parent / "agentindex" / "agent_safety_slugs.json"


def compute_trust_score(stars: int) -> float:
    """min(100, 40 + log10(stars+1) * 15)"""
    return min(100.0, 40.0 + math.log10(stars + 1) * 15.0)


def compute_trust_grade(score: float) -> str:
    if score >= 95:
        return "A+"
    elif score >= 85:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 65:
        return "C"
    elif score >= 50:
        return "D"
    elif score >= 35:
        return "E"
    else:
        return "F"


def make_slug(name: str) -> str:
    """Generate URL slug from agent name (matches _make_slug in agent_safety_pages.py)."""
    slug = name.lower().strip()
    for ch in ['/', '\\', '(', ')', '[', ']', '{', '}', ':', ';', ',', '!', '?',
               '@', '#', '$', '%', '^', '&', '*', '=', '+', '|', '<', '>', '~', '`', "'", '"']:
        slug = slug.replace(ch, '')
    slug = slug.replace(' ', '-').replace('_', '-').replace('.', '-')
    while '--' in slug:
        slug = slug.replace('--', '-')
    return slug.strip('-')


def classify_agent_type(name: str, description: str, topics: list) -> str:
    """Basic agent_type classification from metadata."""
    text_blob = f"{name} {description} {' '.join(topics or [])}".lower()
    if "mcp" in text_blob and "server" in text_blob:
        return "mcp_server"
    if "tool" in text_blob:
        return "tool"
    return "agent"


def guess_category(description: str, topics: list) -> str:
    """Guess a category from description and topics."""
    text_blob = f"{description} {' '.join(topics or [])}".lower()
    mapping = [
        ("security", ["security", "vulnerability", "pentest", "exploit", "audit"]),
        ("finance", ["finance", "trading", "defi", "crypto", "payment"]),
        ("devtools", ["developer", "devtool", "ide", "coding", "code", "development", "build"]),
        ("data", ["data", "database", "analytics", "etl", "pipeline"]),
        ("infrastructure", ["infrastructure", "deploy", "docker", "kubernetes", "cloud", "server", "mcp"]),
        ("content", ["content", "writing", "blog", "marketing", "seo"]),
        ("research", ["research", "science", "academic", "paper"]),
        ("automation", ["automat", "workflow", "orchestrat", "agent"]),
    ]
    for cat, keywords in mapping:
        if any(kw in text_blob for kw in keywords):
            return cat
    return "general"


def main():
    # Load new tools
    data = json.loads(DATA_FILE.read_text())
    new_tools = data.get("new_tools", [])
    if not new_tools:
        print("No new tools found in data file.")
        return

    print(f"Found {len(new_tools)} new tools to add")

    # Load existing slugs
    if SLUGS_FILE.exists():
        existing_slugs = json.loads(SLUGS_FILE.read_text())
    else:
        existing_slugs = []
    slug_set = {s["slug"] for s in existing_slugs}

    added = 0
    skipped = 0
    new_slug_entries = []

    with get_db_session() as session:
        for tool in new_tools:
            source_url = tool.get("url", "")
            name = tool.get("name", "")

            # Check if already exists by source_url
            exists = session.execute(
                text("SELECT 1 FROM agents WHERE source_url = :url LIMIT 1"),
                {"url": source_url}
            ).fetchone()
            if exists:
                skipped += 1
                continue

            stars = tool.get("stars", 0) or 0
            forks = tool.get("forks", 0) or 0
            description = tool.get("description", "") or ""
            topics = tool.get("topics", []) or []
            language = tool.get("language")
            source = tool.get("source", "github")
            author = tool.get("owner", "") or name.split("/")[0] if "/" in name else ""
            display_name = tool.get("display_name", name)
            created_at_str = tool.get("created_at")

            trust_score = round(compute_trust_score(stars), 1)
            trust_grade = compute_trust_grade(trust_score)
            agent_type = classify_agent_type(name, description, topics)
            category = guess_category(description, topics)
            slug = make_slug(name)

            agent_id = str(uuid.uuid4())
            now = datetime.utcnow()

            session.execute(
                text("""
                    INSERT INTO agents (
                        id, source, source_url, source_id, name, description, author,
                        stars, forks, language, category, tags, is_active, crawl_status,
                        first_indexed, last_crawled, trust_score_v2, trust_grade,
                        agent_type, quality_score
                    ) VALUES (
                        :id, :source, :source_url, :source_id, :name, :description, :author,
                        :stars, :forks, :language, :category, :tags, true, 'indexed',
                        :now, :now, :trust_score, :trust_grade,
                        :agent_type, :quality_score
                    )
                    ON CONFLICT (source_url) DO NOTHING
                """),
                {
                    "id": agent_id,
                    "source": source,
                    "source_url": source_url,
                    "source_id": name,
                    "name": name,
                    "description": description[:2000] if description else None,
                    "author": author,
                    "stars": stars,
                    "forks": forks,
                    "language": language,
                    "category": category,
                    "tags": topics if topics else [],
                    "now": now,
                    "trust_score": trust_score,
                    "trust_grade": trust_grade,
                    "agent_type": agent_type,
                    "quality_score": trust_score / 100.0,
                }
            )
            added += 1

            # Build slug entry
            if slug not in slug_set:
                new_slug_entries.append({
                    "slug": slug,
                    "name": name,
                    "category": category,
                    "source": source,
                    "trust_score": trust_score,
                    "trust_grade": trust_grade,
                    "is_verified": False,
                    "stars": stars,
                })
                slug_set.add(slug)

    print(f"Inserted: {added}")
    print(f"Skipped (already existed): {skipped}")

    # Update slugs file
    if new_slug_entries:
        all_slugs = existing_slugs + new_slug_entries
        SLUGS_FILE.write_text(json.dumps(all_slugs, indent=2))
        print(f"Added {len(new_slug_entries)} new slugs to {SLUGS_FILE}")
    else:
        print("No new slugs to add.")

    print("Done.")


if __name__ == "__main__":
    main()
