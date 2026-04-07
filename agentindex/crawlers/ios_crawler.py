#!/usr/bin/env python3
"""iOS App Crawler v2 — uses hundreds of diverse queries for broad coverage."""
import json, logging, re, sys, time, string
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("ios_crawler")

# Hundreds of search queries for broad coverage
QUERIES = (
    # Top apps by name
    ["tiktok","whatsapp","instagram","snapchat","telegram","signal","discord","zoom","teams","slack",
     "temu","shein","amazon","uber","lyft","doordash","venmo","cashapp","paypal","robinhood","coinbase",
     "netflix","spotify","youtube","twitch","disney","hbo","chatgpt","claude","gemini","perplexity",
     "nordvpn","expressvpn","bitwarden","1password","tinder","bumble","hinge","roblox","fortnite","minecraft",
     "duolingo","notion","todoist","canva","capcut","google maps","waze","apple music","shazam","reddit"] +
    # Category terms
    ["social media","messaging app","video call","photo editor","music player","banking","crypto wallet",
     "stock trading","fitness","meditation","health tracker","language learning","education","shopping",
     "food delivery","travel","maps","news","weather","email","calendar","vpn","password manager",
     "antivirus","ai assistant","chatbot","productivity","notes","todo","streaming","podcast","browser",
     "dating","kids safe","calculator","scanner","timer","alarm","flashlight","compass","translator",
     "dictionary","bible","quran","yoga","running","cycling","golf","tennis","chess","sudoku","crossword"] +
    # Single letters + two-letter combos for discovery
    list(string.ascii_lowercase) +
    [a+b for a in "abcdefghijklm" for b in "aeiou"]
)


def crawl(limit=20000):
    logger.info(f"iOS v2 crawl (limit={limit})")
    session = get_session()

    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='ios'")).fetchall()
    seen_slugs = {r[0] for r in rows}
    seen_bundles = set()
    logger.info(f"  Already have {len(seen_slugs)} iOS apps")

    total = 0; new = 0

    for query in QUERIES:
        if total >= limit: break
        try:
            r = http.get("https://itunes.apple.com/search",
                        params={"term": query, "entity": "software", "country": "us", "limit": 200},
                        timeout=15)
            if r.status_code != 200: continue
            results = r.json().get("results", [])
        except Exception as e:
            logger.warning(f"Search '{query}': {e}"); continue

        for app in results:
            if total >= limit: break
            bundle = app.get("bundleId", "")
            if bundle in seen_bundles: continue
            seen_bundles.add(bundle)

            name = app.get("trackName", "")
            if not name: continue
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
            if slug in seen_slugs:
                total += 1; continue
            seen_slugs.add(slug)

            rating = app.get("averageUserRating") or 0
            rating_count = app.get("userRatingCount") or 0

            # Trust scoring
            score = 0
            if rating >= 4.5 and rating_count >= 10000: score += 30
            elif rating >= 4.0 and rating_count >= 1000: score += 25
            elif rating >= 3.5 and rating_count >= 100: score += 15
            elif rating > 0: score += 8
            if rating_count >= 100000: score += 20
            elif rating_count >= 10000: score += 15
            elif rating_count >= 1000: score += 10
            elif rating_count >= 100: score += 5
            release = app.get("currentVersionReleaseDate", "")
            if release:
                try:
                    from datetime import datetime
                    days = (datetime.utcnow() - datetime.fromisoformat(release.replace("Z","+00:00")).replace(tzinfo=None)).days
                    score += 15 if days < 90 else 10 if days < 365 else 3
                except Exception: score += 5
            if app.get("contentAdvisoryRating"): score += 5
            if app.get("sellerName"): score += 5
            if len(app.get("description","")) > 100: score += 5
            score = max(0, min(100, score))
            grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"

            entry = {"name": name, "slug": slug, "registry": "ios",
                    "version": app.get("version"), "description": (app.get("description") or "")[:500],
                    "author": app.get("sellerName") or app.get("artistName") or "",
                    "license": app.get("contentAdvisoryRating") or "",
                    "downloads": rating_count, "stars": int(rating * 20) if rating else 0,
                    "last_updated": release, "repository_url": "",
                    "homepage_url": app.get("trackViewUrl") or "",
                    "dependencies_count": 0, "trust_score": round(score, 1), "trust_grade": grade,
                    "raw_data": json.dumps({"bundleId": bundle, "price": app.get("price",0),
                                           "genre": app.get("primaryGenreName"),
                                           "rating": rating, "ratingCount": rating_count})}
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

        if total % 500 == 0 and new > 0:
            session.commit()
            logger.info(f"  {total} processed, {new} new")
        time.sleep(1)

    session.commit(); session.close()
    logger.info(f"iOS v2 complete: {total} processed, {new} NEW")
    return new

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 20000)
