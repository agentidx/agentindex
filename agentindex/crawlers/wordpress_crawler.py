#!/usr/bin/env python3
"""WordPress.org Plugin Crawler. API: https://api.wordpress.org/plugins/info/1.2/"""
import json, logging, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("wordpress_crawler")

API = "https://api.wordpress.org/plugins/info/1.2/"


def crawl(limit=5000):
    logger.info(f"WordPress crawl (limit={limit})")
    session = get_session(); total = 0; page = 1
    while total < limit:
        try:
            r = http.get(API, params={
                "action": "query_plugins",
                "request[page]": page, "request[per_page]": 250,
                "request[browse]": "popular",
            }, timeout=20)
            if r.status_code != 200: break
            data = r.json()
            plugins = data.get("plugins", [])
            if not plugins: break
        except Exception as e:
            logger.warning(f"Page {page}: {e}"); break

        for p in plugins:
            name = p.get("name", "")
            slug = p.get("slug", "")
            if not slug: continue

            # WP-specific trust factors
            installs = p.get("active_installs") or 0
            rating = p.get("rating") or 0  # 0-100
            num_ratings = p.get("num_ratings") or 0
            resolved = p.get("support_threads_resolved") or 0
            threads = p.get("support_threads") or 1
            tested = p.get("tested") or ""

            entry = {"name": name, "slug": slug, "registry": "wordpress",
                    "version": p.get("version"),
                    "description": (p.get("short_description") or "")[:500],
                    "author": (p.get("author") or "")[:100].replace("<a", "").replace("</a>", ""),
                    "license": "",
                    "downloads": p.get("downloaded") or 0,
                    "stars": int(rating / 20) if rating else 0,  # Convert 0-100 to 0-5 star equiv
                    "last_updated": p.get("last_updated"),
                    "repository_url": "",
                    "homepage_url": p.get("homepage") or f"https://wordpress.org/plugins/{slug}/",
                    "dependencies_count": 0,
                    "raw_data": json.dumps({"active_installs": installs, "rating": rating,
                                           "num_ratings": num_ratings, "tested": tested,
                                           "support_resolved_pct": round(resolved / max(1, threads) * 100)})}
            # Override trust calc with WP-specific scoring
            score = 0
            if installs >= 1_000_000: score += 30
            elif installs >= 100_000: score += 25
            elif installs >= 10_000: score += 20
            elif installs >= 1_000: score += 15
            elif installs > 0: score += 8
            if rating >= 80 and num_ratings >= 50: score += 25
            elif rating >= 60 and num_ratings >= 10: score += 15
            elif rating > 0: score += 8
            if p.get("last_updated"):
                try:
                    from datetime import datetime
                    lu = datetime.strptime(p["last_updated"][:10], "%Y-%m-%d")
                    days = (datetime.utcnow() - lu).days
                    if days < 90: score += 20
                    elif days < 365: score += 12
                    elif days < 730: score += 5
                except Exception: score += 5
            if resolved / max(1, threads) > 0.5: score += 10
            elif resolved > 0: score += 5
            score += 5  # Base metadata
            score = max(0, min(100, score))

            if score >= 80: grade = "A"
            elif score >= 60: grade = "B"
            elif score >= 40: grade = "C"
            else: grade = "D"

            entry["trust_score"] = round(score, 1)
            entry["trust_grade"] = grade

            try:
                session.execute(text("""INSERT INTO software_registry
                    (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                     repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                    VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                     :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                    ON CONFLICT (registry,slug) DO UPDATE SET downloads=EXCLUDED.downloads,trust_score=EXCLUDED.trust_score,
                     trust_grade=EXCLUDED.trust_grade,updated_at=NOW()
                """), entry)
                total += 1
            except Exception as e:
                logger.warning(f"{slug}: {e}"); session.rollback()
        if total % 250 == 0: session.commit(); logger.info(f"  {total} plugins...")
        page += 1; time.sleep(0.5)
    session.commit(); session.close()
    logger.info(f"WordPress complete: {total}"); return total

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)
