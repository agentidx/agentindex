#!/usr/bin/env python3
"""RubyGems Crawler. API: https://rubygems.org/api/v1/search.json?query=*&page=N"""
import json, logging, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("rubygems_crawler")

def crawl(limit=1000):
    logger.info(f"RubyGems crawl (limit={limit})")
    session = get_session(); total = 0; page = 1
    while total < limit:
        try:
            r = http.get("https://rubygems.org/api/v1/search.json",
                        params={"query": "*", "page": page}, timeout=15)
            if r.status_code != 200: break
            gems = r.json()
            if not gems: break
        except Exception as e:
            logger.warning(f"Page {page}: {e}"); break
        for g in gems:
            name = g.get("name", "")
            if not name: continue
            entry = {"name": name, "slug": name.lower(), "registry": "gems",
                    "version": g.get("version"), "description": (g.get("info") or "")[:500],
                    "author": g.get("authors") or "", "license": (g.get("licenses") or [""])[0] if g.get("licenses") else "",
                    "downloads": g.get("downloads") or 0, "stars": 0,
                    "last_updated": None,
                    "repository_url": g.get("source_code_uri"), "homepage_url": g.get("homepage_uri"),
                    "dependencies_count": 0,
                    "raw_data": json.dumps({"version_downloads": g.get("version_downloads")})}
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
    logger.info(f"RubyGems complete: {total}"); return total

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
