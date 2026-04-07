#!/usr/bin/env python3
"""
iOS iTunes Enrichment — enrich iOS apps via iTunes Search API.
For apps already in software_registry with registry='ios', fetch metadata
from iTunes API and calculate trust scores.

Run: python3 -m agentindex.crawlers.ios_itunes_enrichment [limit]
"""

import logging
import sys
import time
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from sqlalchemy import text
from agentindex.db.models import get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("ios_itunes")

ITUNES_SEARCH = "https://itunes.apple.com/search"
ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
BATCH_SIZE = 50
RATE_LIMIT = 0.3  # 300ms between requests


def enrich_one(session, pkg_id, name):
    """Enrich a single iOS app via iTunes Search API."""
    try:
        # Clean name for search
        clean = re.sub(r'[^\w\s]', '', name)[:80].strip()
        if not clean:
            return False

        resp = requests.get(ITUNES_SEARCH, params={
            "term": clean, "entity": "software", "country": "us", "limit": 5
        }, timeout=10)
        if resp.status_code != 200:
            return False

        data = resp.json()
        results = data.get("results", [])
        if not results:
            # Mark as enriched even if not found (avoid re-processing)
            session.execute(text("UPDATE software_registry SET enriched_at = NOW() WHERE id = :id"),
                            {"id": str(pkg_id)})
            return True

        # Find best match (case-insensitive name match)
        app = results[0]
        name_lower = name.lower()
        for r in results:
            if r.get("trackName", "").lower() == name_lower:
                app = r
                break

        # Extract metadata
        description = (app.get("description") or "")[:500]
        author = app.get("artistName") or ""
        version = app.get("version") or ""
        rating = app.get("averageUserRating") or 0
        rating_count = app.get("userRatingCount") or 0
        age_rating = app.get("contentAdvisoryRating") or ""
        price = app.get("price") or 0
        url = app.get("trackViewUrl") or ""

        session.execute(text("""
            UPDATE software_registry SET
                description = COALESCE(NULLIF(:desc, ''), description),
                author = COALESCE(NULLIF(:auth, ''), author),
                latest_version = COALESCE(NULLIF(:ver, ''), latest_version),
                homepage_url = COALESCE(NULLIF(:url, ''), homepage_url),
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id),
            "desc": description,
            "auth": author[:200],
            "ver": version[:50],
            "url": url[:500],
        })
        return True

    except requests.exceptions.Timeout:
        return False
    except Exception as e:
        log.warning(f"Error: {name}: {e}")
        return False


def calculate_ios_trust(session, pkg_id):
    """Calculate trust score for iOS app."""
    row = session.execute(text("""
        SELECT downloads, description, author, deprecated
        FROM software_registry WHERE id = :id
    """), {"id": str(pkg_id)}).fetchone()
    if not row:
        return

    dl = row[0] or 0
    description = row[1] or ""
    author = row[2] or ""
    deprecated = row[3]

    if deprecated:
        session.execute(text("UPDATE software_registry SET trust_score=10, trust_grade='F' WHERE id=:id"),
                        {"id": str(pkg_id)})
        return

    # Security: base 60 for iOS (App Store review process)
    security = 60

    # Popularity based on downloads/installs
    popularity = 0
    if dl > 10_000_000: popularity = 100
    elif dl > 1_000_000: popularity = 90
    elif dl > 100_000: popularity = 75
    elif dl > 10_000: popularity = 60
    elif dl > 1_000: popularity = 45
    elif dl > 100: popularity = 30
    elif dl > 0: popularity = 15

    # Quality
    quality = 40
    if len(description) > 50: quality += 15
    if author: quality += 10
    quality = min(100, quality)

    community = 40
    maintenance = 50

    total = round(security * 0.25 + maintenance * 0.20 + popularity * 0.20 + community * 0.15 + quality * 0.20, 1)
    grade = "A+" if total >= 90 else "A" if total >= 85 else "A-" if total >= 80 else "B+" if total >= 75 else "B" if total >= 70 else "B-" if total >= 65 else "C+" if total >= 60 else "C" if total >= 55 else "C-" if total >= 50 else "D" if total >= 40 else "F"

    session.execute(text("""
        UPDATE software_registry SET trust_score=:s, trust_grade=:g,
            security_score=:sec, maintenance_score=:m, popularity_score=:p, community_score=:c, quality_score=:q
        WHERE id=:id
    """), {"id": str(pkg_id), "s": total, "g": grade,
           "sec": round(security, 1), "m": round(maintenance, 1),
           "p": round(popularity, 1), "c": round(community, 1), "q": round(quality, 1)})


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50000

    session = get_session()
    try:
        session.execute(text("SET statement_timeout = '10s'"))
        rows = session.execute(text("""
            SELECT id, name FROM software_registry
            WHERE registry = 'ios' AND enriched_at IS NULL
            ORDER BY name ASC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
        session.execute(text("SET statement_timeout = '10s'"))

        total = len(rows)
        log.info(f"iOS iTunes enrichment: {total} apps (limit={limit})")

        done = 0
        for i, pkg in enumerate(rows):
            try:
                if enrich_one(session, pkg[0], pkg[1]):
                    calculate_ios_trust(session, pkg[0])
                    done += 1
            except Exception as e:
                log.warning(f"Error processing {pkg[1]}: {e}")
                try:
                    session.rollback()
                except Exception:
                    pass

            if (i + 1) % BATCH_SIZE == 0:
                session.commit()
                if (i + 1) % 500 == 0:
                    log.info(f"Progress: {done}/{total} ({done * 100 // max(1, total)}%)")

            time.sleep(RATE_LIMIT)

        session.commit()
        log.info(f"iOS enrichment complete: {done}/{total}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
