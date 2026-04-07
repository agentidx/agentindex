#!/usr/bin/env python3
"""RubyGems Bulk Crawler — letter-by-letter search for ALL gems."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text
import string

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("gems_bulk")

STATE_FILE = Path(__file__).parent.parent.parent / "data" / "gems_bulk_state.json"

# All single letters + digits + two-letter combos for broad coverage
QUERIES = list(string.ascii_lowercase) + list(string.digits) + \
          [a+b for a in string.ascii_lowercase for b in string.ascii_lowercase[:10]]


def _load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: pass
    return {"query_index": 0}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def crawl(limit=50000):
    logger.info(f"RubyGems bulk crawl (limit={limit})")
    state = _load_state()

    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='gems'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} gems")

    total = 0; new = 0
    qi = state.get("query_index", 0)

    for i, query in enumerate(QUERIES):
        if i < qi: continue
        if new >= limit: break

        page = 1
        while new < limit:
            try:
                r = http.get("https://rubygems.org/api/v1/search.json",
                            params={"query": query, "page": page}, timeout=15)
                if r.status_code == 429:
                    logger.info("  Rate limited, waiting 10s...")
                    time.sleep(10); continue
                if r.status_code != 200: break
                gems = r.json()
                if not gems: break
            except Exception as e:
                logger.warning(f"Query '{query}' p{page}: {e}"); break

            for g in gems:
                name = g.get("name", "")
                if not name: continue
                slug = name.lower()
                if slug in seen: total += 1; continue
                seen.add(slug)

                entry = {"name": name, "slug": slug, "registry": "gems",
                        "version": g.get("version"),
                        "description": (g.get("info") or "")[:500],
                        "author": (g.get("authors") or "")[:100],
                        "license": ((g.get("licenses") or [""])[0] if g.get("licenses") else "")[:100],
                        "downloads": g.get("downloads") or 0, "stars": 0,
                        "last_updated": None,
                        "repository_url": (g.get("source_code_uri") or "")[:200],
                        "homepage_url": g.get("homepage_uri") or f"https://rubygems.org/gems/{name}",
                        "dependencies_count": 0,
                        "raw_data": json.dumps({"version_downloads": g.get("version_downloads")})}
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

            page += 1
            if new % 2000 == 0 and new > 0:
                session.commit()
                logger.info(f"  Query '{query}' p{page}: {total} processed, {new} new")
            time.sleep(1)

        state["query_index"] = i + 1
        _save_state(state)

    session.commit(); session.close()
    logger.info(f"Gems bulk complete: {total} processed, {new} NEW")
    return new


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 50000)
