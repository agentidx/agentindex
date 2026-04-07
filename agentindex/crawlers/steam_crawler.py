#!/usr/bin/env python3
"""Steam Crawler v2 — SteamSpy as primary, Steam Store API for enrichment."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("steam_crawler")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NerqBot/1.0)", "Accept": "application/json"}


def crawl(limit=10000):
    logger.info(f"Steam v2 crawl (limit={limit})")
    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='steam'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} Steam games")

    total = 0; new = 0

    # Use SteamSpy paginated API as primary source
    page = 0
    while total < limit:
        try:
            r = http.get("https://steamspy.com/api.php",
                        params={"request": "all", "page": page},
                        headers=HEADERS, timeout=15)
            if r.status_code != 200:
                logger.warning(f"SteamSpy page {page}: HTTP {r.status_code}"); break
            data = r.json()
            if not data: break
        except Exception as e:
            logger.warning(f"SteamSpy page {page}: {e}"); break

        for appid_str, info in data.items():
            if total >= limit: break
            name = info.get("name", "")
            if not name or len(name) < 2: continue
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            if not slug or slug in seen: total += 1; continue
            seen.add(slug)

            owners_str = info.get("owners", "0 .. 0")
            try:
                owners_low = int(owners_str.split("..")[0].strip().replace(",", ""))
            except (ValueError, IndexError):
                owners_low = 0

            positive = info.get("positive", 0)
            negative = info.get("negative", 0)
            total_reviews = positive + negative
            pos_pct = (positive / total_reviews * 100) if total_reviews > 0 else 0

            # Trust scoring
            trust = 0
            if owners_low >= 10000000: trust += 25
            elif owners_low >= 1000000: trust += 20
            elif owners_low >= 100000: trust += 15
            elif owners_low >= 10000: trust += 10
            elif owners_low > 0: trust += 5
            if pos_pct >= 90 and total_reviews >= 1000: trust += 25
            elif pos_pct >= 80 and total_reviews >= 100: trust += 20
            elif pos_pct >= 70: trust += 12
            elif total_reviews > 0: trust += 5
            if info.get("developer"): trust += 5
            trust += 10  # On Steam
            trust = max(0, min(100, trust))
            grade = "A" if trust >= 80 else "B" if trust >= 60 else "C" if trust >= 40 else "D"

            try:
                price = int(info.get("price", 0) or 0)
            except (ValueError, TypeError):
                price = 0
            price_str = f"${price/100:.2f}" if price else "Free"

            entry = {"name": name, "slug": slug, "registry": "steam",
                    "version": None, "description": f"{name} — Steam game. {price_str}. {pos_pct:.0f}% positive reviews.",
                    "author": (info.get("developer") or "")[:100],
                    "license": "", "downloads": owners_low,
                    "stars": int(pos_pct) if pos_pct else 0,
                    "last_updated": None, "repository_url": "",
                    "homepage_url": f"https://store.steampowered.com/app/{appid_str}/",
                    "dependencies_count": 0,
                    "trust_score": round(trust, 1), "trust_grade": grade,
                    "raw_data": json.dumps({"appid": appid_str, "owners": owners_str,
                                           "positive": positive, "negative": negative,
                                           "price": price, "genre": info.get("genre", "")})}
            try:
                session.execute(text("""INSERT INTO software_registry
                    (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                     repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                    VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                     :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                    ON CONFLICT (registry,slug) DO NOTHING
                """), entry)
                new += 1
            except Exception:
                session.rollback()
            total += 1

        if new % 500 == 0 and new > 0:
            session.commit()
            logger.info(f"  {total} processed, {new} new games (page {page})")
        page += 1
        time.sleep(1)

    session.commit(); session.close()
    logger.info(f"Steam v2 complete: {total} processed, {new} NEW games")
    return new


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 10000)
