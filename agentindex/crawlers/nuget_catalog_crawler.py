#!/usr/bin/env python3
"""NuGet Catalog Crawler — uses catalog API to get ALL packages."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("nuget_catalog")

CATALOG_INDEX = "https://api.nuget.org/v3/catalog0/index.json"
STATE_FILE = Path(__file__).parent.parent.parent / "data" / "nuget_catalog_state.json"


def _load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: pass
    return {"last_page": 0, "seen_ids": []}


def _save_state(state):
    state["seen_ids"] = state["seen_ids"][-200000:]
    STATE_FILE.write_text(json.dumps(state))


def crawl(limit=100000):
    logger.info(f"NuGet catalog crawl (limit={limit})")
    state = _load_state()
    seen = set(state.get("seen_ids", []))

    # Load existing from DB
    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='nuget'")).fetchall()
    for r in rows:
        seen.add(r[0])
    logger.info(f"  Already have {len(seen)} NuGet packages")

    # Fetch catalog index
    try:
        r = http.get(CATALOG_INDEX, timeout=30)
        pages = r.json().get("items", [])
        logger.info(f"  Catalog has {len(pages)} pages")
    except Exception as e:
        logger.error(f"Catalog index error: {e}"); return 0

    total = 0; new = 0
    start_page = state.get("last_page", 0)

    for i, page_info in enumerate(pages):
        if i < start_page: continue
        if new >= limit: break

        page_url = page_info.get("@id", "")
        if not page_url: continue

        try:
            r = http.get(page_url, timeout=15)
            if r.status_code != 200: continue
            items = r.json().get("items", [])
        except Exception:
            continue

        for item in items:
            if new >= limit: break
            pkg_id = item.get("nuget:id", "")
            if not pkg_id: continue
            slug = pkg_id.lower().replace(".", "-")
            if slug in seen: total += 1; continue
            seen.add(slug)

            ver = item.get("nuget:version", "")
            desc = (item.get("nuget:description") or "")[:500]
            authors = item.get("nuget:authors") or ""

            entry = {"name": pkg_id, "slug": slug, "registry": "nuget",
                    "version": ver, "description": desc,
                    "author": str(authors)[:100], "license": "",
                    "downloads": 0, "stars": 0,
                    "last_updated": (item.get("commitTimeStamp") or "")[:19],
                    "repository_url": "",
                    "homepage_url": f"https://www.nuget.org/packages/{pkg_id}",
                    "dependencies_count": 0,
                    "raw_data": json.dumps({"catalogPage": i})}
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

        if new % 5000 == 0 and new > 0:
            session.commit()
            logger.info(f"  Page {i}/{len(pages)}: {total} processed, {new} new")

        state["last_page"] = i
        time.sleep(0.3)

    session.commit(); session.close()
    state["seen_ids"] = list(seen)
    _save_state(state)
    logger.info(f"NuGet catalog complete: {total} processed, {new} NEW")
    return new


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 100000)
