#!/usr/bin/env python3
"""Crates.io Bulk Loader — downloads full DB dump and loads ALL crates."""
import csv, gzip, io, json, logging, os, re, sys, tarfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("crates_bulk")

DUMP_URL = "https://static.crates.io/db-dump.tar.gz"
DUMP_PATH = "/tmp/crates-db-dump.tar.gz"


def crawl(limit=150000):
    logger.info(f"Crates bulk load (limit={limit})")

    # Download dump if not cached
    if not os.path.exists(DUMP_PATH) or os.path.getsize(DUMP_PATH) < 1000000:
        logger.info("Downloading crates.io dump...")
        r = http.get(DUMP_URL, stream=True, timeout=120)
        if r.status_code != 200:
            logger.error(f"Download failed: {r.status_code}"); return 0
        with open(DUMP_PATH, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        logger.info(f"  Downloaded {os.path.getsize(DUMP_PATH) / 1024 / 1024:.0f} MB")

    # Extract and parse crates.csv
    logger.info("Extracting crates.csv from dump...")
    crates_data = []
    try:
        csv.field_size_limit(1024 * 1024)  # 1MB field limit
        with tarfile.open(DUMP_PATH, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("/data/crates.csv"):
                    f = tar.extractfile(member)
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        crates_data.append(row)
                    break
    except Exception as e:
        logger.error(f"Extract error: {e}"); return 0

    logger.info(f"  Found {len(crates_data)} crates in dump")

    # Load into DB
    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='crates'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} crates")

    total = 0; new = 0
    for row in crates_data[:limit]:
        name = row.get("name", "")
        if not name: continue
        slug = name.lower()
        if slug in seen:
            total += 1; continue
        seen.add(slug)

        downloads = int(row.get("downloads", 0) or 0)
        desc = (row.get("description") or "")[:500]
        repo = row.get("repository") or ""
        homepage = row.get("homepage") or ""
        created = row.get("created_at", "")[:19]
        updated = row.get("updated_at", "")[:19]

        entry = {"name": name, "slug": slug, "registry": "crates",
                "version": None, "description": desc,
                "author": "", "license": "",
                "downloads": downloads, "stars": 0,
                "last_updated": updated if updated else None,
                "repository_url": repo[:200], "homepage_url": homepage[:200] or f"https://crates.io/crates/{name}",
                "dependencies_count": 0,
                "raw_data": json.dumps({"created_at": created})}
        entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)

        try:
            session.execute(text("""INSERT INTO software_registry
                (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                 repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                 :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                ON CONFLICT (registry,slug) DO UPDATE SET downloads=EXCLUDED.downloads,trust_score=EXCLUDED.trust_score,updated_at=NOW()
            """), entry)
            new += 1
        except Exception:
            session.rollback()
        total += 1

        if new % 5000 == 0 and new > 0:
            session.commit()
            logger.info(f"  {total} processed, {new} new")

    session.commit(); session.close()
    logger.info(f"Crates bulk complete: {total} processed, {new} NEW")
    return new


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 150000)
