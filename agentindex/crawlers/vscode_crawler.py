#!/usr/bin/env python3
"""VS Code Marketplace Crawler. POST to gallery/extensionquery API."""
import json, logging, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("vscode_crawler")

API = "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json;api-version=7.1-preview.1"}


def _get_stat(stats, name):
    for s in (stats or []):
        if s.get("statisticName") == name:
            return s.get("value", 0)
    return 0


def crawl(limit=1000):
    logger.info(f"VS Code crawl (limit={limit})")
    session = get_session(); total = 0; page = 1
    while total < limit:
        body = {"filters": [{"criteria": [{"filterType": 8, "value": "Microsoft.VisualStudio.Code"}],
                            "pageNumber": page, "pageSize": min(100, limit - total),
                            "sortBy": 4, "sortOrder": 0}],  # 4=installs
                "assetTypes": [], "flags": 914}
        try:
            r = http.post(API, json=body, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                logger.warning(f"API error: {r.status_code}"); break
            results = r.json().get("results", [{}])[0].get("extensions", [])
            if not results: break
        except Exception as e:
            logger.warning(f"Request error: {e}"); break

        for ext in results:
            name = ext.get("extensionName", "")
            publisher = ext.get("publisher", {}).get("publisherName", "")
            if not name: continue
            full_name = f"{publisher}.{name}" if publisher else name
            slug = full_name.lower().replace(" ", "-")

            stats = ext.get("statistics", [])
            installs = int(_get_stat(stats, "install"))
            rating = _get_stat(stats, "averagerating")

            versions = ext.get("versions", [])
            last_updated = versions[0].get("lastUpdated") if versions else None

            entry = {"name": full_name, "slug": slug, "registry": "vscode",
                    "version": versions[0].get("version") if versions else None,
                    "description": (ext.get("shortDescription") or "")[:500],
                    "author": publisher, "license": "",
                    "downloads": installs, "stars": 0,
                    "last_updated": last_updated,
                    "repository_url": "", "homepage_url": f"https://marketplace.visualstudio.com/items?itemName={full_name}",
                    "dependencies_count": 0,
                    "raw_data": json.dumps({"rating": rating, "categories": ext.get("categories", []),
                                           "tags": ext.get("tags", [])[:10]})}
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
                logger.warning(f"{full_name}: {e}"); session.rollback()
        if total % 100 == 0: session.commit(); logger.info(f"  {total}...")
        page += 1; time.sleep(1)
    session.commit(); session.close()
    logger.info(f"VS Code complete: {total}"); return total

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
