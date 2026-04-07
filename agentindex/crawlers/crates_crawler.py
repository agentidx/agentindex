#!/usr/bin/env python3
"""Crates.io Crawler. API: https://crates.io/api/v1/crates?page=N&per_page=100&sort=downloads"""
import json, logging, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("crates_crawler")

def crawl(limit=1000):
    logger.info(f"Crates crawl (limit={limit})")
    session = get_session(); total = 0; page = 1
    while total < limit:
        try:
            r = http.get("https://crates.io/api/v1/crates",
                        params={"page": page, "per_page": 100, "sort": "downloads"},
                        headers={"User-Agent": "Nerq Trust Crawler (nerq.ai)"}, timeout=15)
            if r.status_code != 200: break
            crates = r.json().get("crates", [])
            if not crates: break
        except Exception as e:
            logger.warning(f"Page {page}: {e}"); break
        for c in crates:
            name = c.get("id", "")
            if not name: continue
            entry = {"name": name, "slug": name.lower(), "registry": "crates",
                    "version": c.get("newest_version"), "description": (c.get("description") or "")[:500],
                    "author": "", "license": "",
                    "downloads": c.get("downloads") or 0, "stars": 0,
                    "last_updated": c.get("updated_at"),
                    "repository_url": c.get("repository"), "homepage_url": c.get("homepage"),
                    "dependencies_count": 0,
                    "raw_data": json.dumps({"max_version": c.get("max_version")})}
            entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)
            try:
                session.execute(text("""INSERT INTO software_registry
                    (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                     repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                    VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                     :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                    ON CONFLICT (registry,slug) DO UPDATE SET downloads=EXCLUDED.downloads,trust_score=EXCLUDED.trust_score,updated_at=NOW()
                """), entry)
                total += 1
            except Exception as e:
                logger.warning(f"{name}: {e}"); session.rollback()
        if total % 100 == 0: session.commit(); logger.info(f"  {total}...")
        page += 1; time.sleep(1)
    session.commit(); session.close()
    logger.info(f"Crates complete: {total}"); return total

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
