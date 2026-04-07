#!/usr/bin/env python3
"""Packagist (PHP) Crawler. Search: https://packagist.org/search.json?q=&page=N"""
import json, logging, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("packagist_crawler")


def crawl(limit=1000):
    logger.info(f"Packagist crawl (limit={limit})")
    session = get_session(); total = 0; page = 1
    while total < limit:
        try:
            # Packagist needs a real query — cycle through popular terms
            queries = ["laravel", "symfony", "php", "wordpress", "api", "json", "http", "log",
                       "database", "cache", "queue", "auth", "test", "mail", "image", "pdf",
                       "csv", "xml", "aws", "guzzle", "monolog", "doctrine", "twig", "carbon"]
            q = queries[(page - 1) % len(queries)]
            r = http.get("https://packagist.org/search.json",
                        params={"q": q, "page": ((page - 1) // len(queries)) + 1}, timeout=15)
            if r.status_code != 200: break
            data = r.json()
            results = data.get("results", [])
            if not results: break
        except Exception as e:
            logger.warning(f"Page {page}: {e}"); break

        for pkg in results:
            name = pkg.get("name", "")
            if not name: continue
            slug = name.lower().replace("/", "-")
            entry = {"name": name, "slug": slug, "registry": "packagist",
                    "version": None, "description": (pkg.get("description") or "")[:500],
                    "author": name.split("/")[0] if "/" in name else "",
                    "license": "",
                    "downloads": pkg.get("downloads") or 0, "stars": pkg.get("favers") or 0,
                    "last_updated": None,
                    "repository_url": pkg.get("repository") or pkg.get("url"),
                    "homepage_url": f"https://packagist.org/packages/{name}",
                    "dependencies_count": 0,
                    "raw_data": json.dumps({"virtual": pkg.get("virtual", False)})}
            entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)
            try:
                session.execute(text("""INSERT INTO software_registry
                    (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                     repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                    VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                     :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                    ON CONFLICT (registry,slug) DO UPDATE SET downloads=EXCLUDED.downloads,stars=EXCLUDED.stars,trust_score=EXCLUDED.trust_score,updated_at=NOW()
                """), entry)
                total += 1
            except Exception as e:
                logger.warning(f"{name}: {e}"); session.rollback()
        if total % 100 == 0: session.commit(); logger.info(f"  {total}...")
        page += 1; time.sleep(1)
        if not data.get("next"): break  # No more pages
    session.commit(); session.close()
    logger.info(f"Packagist complete: {total}"); return total

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
