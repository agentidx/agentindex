#!/usr/bin/env python3
"""Packagist Bulk Crawler — uses list.json for ALL 350K+ package names."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("packagist_bulk")

STATE_FILE = Path(__file__).parent.parent.parent / "data" / "packagist_bulk_state.json"


def _load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: pass
    return {"offset": 0}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def crawl(limit=50000):
    logger.info(f"Packagist bulk crawl (limit={limit})")
    state = _load_state()

    # Get ALL package names
    logger.info("Fetching package list...")
    try:
        r = http.get("https://packagist.org/packages/list.json", timeout=30)
        all_names = r.json().get("packageNames", [])
        logger.info(f"  {len(all_names)} packages in Packagist")
    except Exception as e:
        logger.error(f"List fetch error: {e}"); return 0

    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='packagist'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} Packagist packages")

    offset = state.get("offset", 0)
    total = 0; new = 0

    for i, name in enumerate(all_names[offset:]):
        if new >= limit: break
        slug = name.lower().replace("/", "-")
        if slug in seen:
            total += 1; continue

        # Fetch package details
        try:
            r = http.get(f"https://packagist.org/packages/{name}.json", timeout=10)
            if r.status_code != 200: total += 1; continue
            pkg = r.json().get("package", {})
        except Exception:
            total += 1; continue

        desc = (pkg.get("description") or "")[:500]
        dl = 0
        for ver_data in (pkg.get("versions") or {}).values():
            if isinstance(ver_data, dict):
                # Get latest version downloads
                break

        # Use package-level stats
        downloads = pkg.get("downloads", {})
        if isinstance(downloads, dict):
            dl = downloads.get("total", 0)
        elif isinstance(downloads, int):
            dl = downloads

        favers = pkg.get("favers", 0) or 0
        repo = pkg.get("repository") or ""

        entry = {"name": name, "slug": slug, "registry": "packagist",
                "version": None, "description": desc,
                "author": name.split("/")[0] if "/" in name else "",
                "license": "",
                "downloads": dl, "stars": favers,
                "last_updated": None,
                "repository_url": repo[:200],
                "homepage_url": f"https://packagist.org/packages/{name}",
                "dependencies_count": 0,
                "raw_data": json.dumps({"favers": favers})}
        entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)

        try:
            session.execute(text("""INSERT INTO software_registry
                (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                 repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                 :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                ON CONFLICT (registry,slug) DO UPDATE SET downloads=EXCLUDED.downloads,trust_score=EXCLUDED.trust_score,updated_at=NOW()
            """), entry)
            new += 1; seen.add(slug)
        except Exception:
            session.rollback()
        total += 1

        if new % 1000 == 0 and new > 0:
            session.commit()
            state["offset"] = offset + i
            _save_state(state)
            logger.info(f"  {total} processed, {new} new")
        time.sleep(0.5)  # Respect rate limits

    session.commit(); session.close()
    state["offset"] = offset + total
    _save_state(state)
    logger.info(f"Packagist bulk complete: {total} processed, {new} NEW")
    return new


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 50000)
