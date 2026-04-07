#!/usr/bin/env python3
"""
Android Google Play Crawler — crawls top apps per category.
Uses google-play-scraper library.

Run: python3 -m agentindex.crawlers.android_play_crawler [limit_per_category]
"""

import logging
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("android_play")

BATCH_SIZE = 50

CATEGORIES = [
    "SOCIAL", "COMMUNICATION", "PHOTOGRAPHY", "VIDEO_PLAYERS",
    "SHOPPING", "FINANCE", "HEALTH_AND_FITNESS", "FOOD_AND_DRINK",
    "TRAVEL_AND_LOCAL", "PRODUCTIVITY", "EDUCATION", "GAME_ACTION",
    "GAME_PUZZLE", "GAME_ARCADE", "GAME_CASUAL", "GAME_STRATEGY",
    "NEWS_AND_MAGAZINES", "WEATHER", "TOOLS", "ENTERTAINMENT",
    "MUSIC_AND_AUDIO", "SPORTS", "BUSINESS", "MAPS_AND_NAVIGATION",
    "LIFESTYLE", "MEDICAL", "BOOKS_AND_REFERENCE", "PERSONALIZATION",
    "HOUSE_AND_HOME", "DATING", "PARENTING", "AUTO_AND_VEHICLES",
    "ART_AND_DESIGN", "BEAUTY", "EVENTS", "COMICS",
]

UPSERT_SQL = text("""
    INSERT INTO software_registry
        (id, name, slug, registry, description, author, downloads, enriched_at, created_at,
         trust_score, trust_grade, security_score, popularity_score, is_king)
    VALUES (:id, :name, :slug, 'android', :desc, :auth, :dl, NOW(), NOW(),
            :score, :grade, :sec, :pop, :king)
    ON CONFLICT (registry, slug) DO UPDATE SET
        description = COALESCE(NULLIF(EXCLUDED.description, ''), software_registry.description),
        author = COALESCE(NULLIF(EXCLUDED.author, ''), software_registry.author),
        downloads = GREATEST(COALESCE(software_registry.downloads, 0), EXCLUDED.downloads),
        trust_score = GREATEST(COALESCE(software_registry.trust_score, 0), EXCLUDED.trust_score),
        trust_grade = CASE WHEN EXCLUDED.trust_score > COALESCE(software_registry.trust_score, 0)
                      THEN EXCLUDED.trust_grade ELSE software_registry.trust_grade END,
        is_king = EXCLUDED.is_king OR software_registry.is_king,
        enriched_at = NOW()
""")


def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:100]


def score_from_app(app_data):
    score = 50
    _inst = app_data.get("realInstalls") or app_data.get("installs") or 0
    installs = int(str(_inst).replace(",", "").replace("+", "")) if _inst else 0
    rating = float(app_data.get("score") or 0)

    if installs > 1_000_000_000: score += 25
    elif installs > 100_000_000: score += 20
    elif installs > 10_000_000: score += 15
    elif installs > 1_000_000: score += 10
    elif installs > 100_000: score += 5

    if rating >= 4.5: score += 15
    elif rating >= 4.0: score += 10
    elif rating >= 3.5: score += 5
    elif rating < 3.0: score -= 5

    return max(20, min(95, score))


def grade(score):
    if score >= 90: return "A+"
    if score >= 85: return "A"
    if score >= 80: return "A-"
    if score >= 75: return "B+"
    if score >= 70: return "B"
    if score >= 65: return "B-"
    if score >= 60: return "C+"
    if score >= 55: return "C"
    if score >= 50: return "C-"
    if score >= 40: return "D"
    return "F"


def main():
    limit_per_cat = int(sys.argv[1]) if len(sys.argv) > 1 else 200

    try:
        from google_play_scraper import search
    except ImportError:
        log.error("Install: pip3 install google-play-scraper")
        sys.exit(1)

    session = get_session()
    session.execute(text("SET statement_timeout = '10s'"))

    total = 0
    seen = set()
    batch_count = 0
    king_count = 0

    for cat in CATEGORIES:
        try:
            log.info(f"Searching category: {cat}")
            results = search(cat.replace("_", " ").lower(), n_hits=limit_per_cat, lang="en", country="us")

            for app_data in results:
                app_id = app_data.get("appId", "")
                if app_id in seen:
                    continue
                seen.add(app_id)

                name = app_data.get("title", "")
                slug = slugify(name)
                if not slug or len(slug) < 2:
                    continue

                _raw_inst = app_data.get("realInstalls") or app_data.get("installs") or 0
                installs = int(str(_raw_inst).replace(",", "").replace("+", "")) if _raw_inst else 0
                s = score_from_app(app_data)
                is_king = installs > 10_000_000 or king_count < 5000

                try:
                    session.execute(UPSERT_SQL, {
                        "id": str(uuid.uuid4()),
                        "name": name[:255],
                        "slug": slug,
                        "desc": (app_data.get("description") or "")[:500],
                        "auth": (app_data.get("developer") or "")[:200],
                        "dl": installs,
                        "score": s,
                        "grade": grade(s),
                        "sec": s,
                        "pop": min(95, 50 + installs // 10_000_000) if installs else 50,
                        "king": is_king,
                    })
                    total += 1
                    batch_count += 1
                    if is_king:
                        king_count += 1
                except Exception as e:
                    log.warning(f"Error {name}: {e}")
                    session.rollback()

                if batch_count >= BATCH_SIZE:
                    session.commit()
                    batch_count = 0

            log.info(f"  {cat}: {len(results)} results, {total} total unique")
            time.sleep(2)  # Be polite

        except Exception as e:
            log.warning(f"Category {cat} failed: {e}")
            time.sleep(5)

    if batch_count > 0:
        session.commit()

    session.close()
    log.info(f"Android Play crawler complete: {total} apps ({king_count} kings)")


if __name__ == "__main__":
    main()
