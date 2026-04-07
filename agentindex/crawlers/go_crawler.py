#!/usr/bin/env python3
"""Go Module Crawler v2 — uses index.golang.org stream + pkg.go.dev search."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("go_crawler")


def crawl(limit=50000):
    logger.info(f"Go v2 crawl (limit={limit})")
    session = get_session()

    # Load existing to skip
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='go'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} Go modules")

    total = 0; new = 0
    since = "2019-04-10T19:08:52.997264Z"

    while total < limit:
        try:
            r = http.get(f"https://index.golang.org/index",
                        params={"since": since, "limit": 2000},
                        timeout=30)
            if r.status_code != 200:
                logger.warning(f"Index API error: {r.status_code}"); break
            lines = r.text.strip().split("\n")
            if not lines or lines == [""]: break
        except Exception as e:
            logger.warning(f"Index error: {e}"); break

        for line in lines:
            try:
                entry_data = json.loads(line)
            except json.JSONDecodeError:
                continue

            mod_path = entry_data.get("Path", "")
            version = entry_data.get("Version", "")
            ts = entry_data.get("Timestamp", "")
            since = ts  # Update cursor

            if not mod_path: continue
            slug = mod_path.lower().replace("/", "-").replace(".", "-")
            slug = re.sub(r"[^a-z0-9-]", "", slug).strip("-")

            if slug in seen:
                total += 1; continue
            seen.add(slug)

            short = mod_path.split("/")[-1] if "/" in mod_path else mod_path
            author = mod_path.split("/")[1] if mod_path.count("/") >= 1 else ""

            entry = {"name": mod_path, "slug": slug, "registry": "go",
                    "version": version, "description": f"Go module: {short}",
                    "author": author, "license": "", "downloads": 0, "stars": 0,
                    "last_updated": ts[:19] if ts else None,
                    "repository_url": f"https://{mod_path}" if not mod_path.startswith("http") else mod_path,
                    "homepage_url": f"https://pkg.go.dev/{mod_path}",
                    "dependencies_count": 0,
                    "raw_data": json.dumps({"version": version})}
            entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)

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

        if total % 2000 == 0:
            session.commit()
            logger.info(f"  {total} processed, {new} new")
        time.sleep(0.3)

    session.commit(); session.close()
    logger.info(f"Go v2 complete: {total} processed, {new} NEW")
    return new

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 50000)
