#!/usr/bin/env python3
"""npm Bulk Crawler — uses _all_docs replication endpoint for ALL 2M+ packages."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("npm_bulk")

ALL_DOCS = "https://replicate.npmjs.com/_all_docs"
CHANGES = "https://replicate.npmjs.com/_changes"
REGISTRY = "https://registry.npmjs.org"
STATE_FILE = Path(__file__).parent.parent.parent / "data" / "npm_bulk_state.json"


def _load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: pass
    return {"start_key": "", "fetched_names": False, "names_file": ""}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def _fetch_all_names():
    """Fetch ALL npm package names from _all_docs endpoint."""
    names_file = Path("/tmp/npm_all_names.json")
    if names_file.exists() and names_file.stat().st_size > 10000000:
        logger.info("Loading cached package names...")
        return json.loads(names_file.read_text())

    logger.info("Fetching ALL npm package names via _changes feed...")
    all_names = []
    since = 0
    batch = 0
    while True:
        try:
            r = http.get(CHANGES, params={"since": since, "limit": 5000}, timeout=60)
            if r.status_code != 200:
                logger.warning(f"_changes HTTP {r.status_code}"); break
            data = r.json()
            results = data.get("results", [])
            if not results: break
        except Exception as e:
            logger.warning(f"Fetch error: {e}"); break

        for item in results:
            name = item.get("id", "")
            if name and not name.startswith("_") and len(name) > 1:
                all_names.append(name)

        since = data.get("last_seq", since)
        batch += 1
        if batch % 100 == 0:
            logger.info(f"  Fetched {len(all_names)} names (batch {batch}, seq {since})...")

        if len(results) < 5000:
            break  # Last page
        time.sleep(0.1)

    logger.info(f"  Total: {len(all_names)} package names")
    names_file.write_text(json.dumps(all_names))
    return all_names


def crawl(limit=100000):
    logger.info(f"npm bulk crawl (limit={limit})")
    state = _load_state()

    # Get all names
    all_names = _fetch_all_names()
    if not all_names:
        logger.error("No names fetched"); return 0

    # Load existing
    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='npm'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} npm packages. {len(all_names)} total available.")

    # Filter to only new packages
    new_names = []
    for name in all_names:
        slug = name.lower().replace("/", "-").replace("@", "").replace(" ", "-")
        slug = re.sub(r"[^a-z0-9-]", "", slug).strip("-")
        if slug and slug not in seen:
            new_names.append((name, slug))

    logger.info(f"  {len(new_names)} new packages to crawl")

    total = 0; new = 0
    for name, slug in new_names[:limit]:
        # Fetch package details
        try:
            r = http.get(f"{REGISTRY}/{name}", timeout=8)
            if r.status_code != 200:
                total += 1; continue
            pkg = r.json()
        except Exception:
            total += 1; continue

        latest = pkg.get("dist-tags", {}).get("latest", "")
        version_data = pkg.get("versions", {}).get(latest, {}) if latest else {}
        desc = (pkg.get("description") or version_data.get("description") or "")[:500]
        author = ""
        auth = pkg.get("author")
        if isinstance(auth, dict): author = auth.get("name", "")
        elif isinstance(auth, str): author = auth[:100]
        license_val = pkg.get("license")
        if isinstance(license_val, dict): license_val = license_val.get("type", "")
        repo = ""
        repo_data = pkg.get("repository")
        if isinstance(repo_data, dict): repo = repo_data.get("url", "")[:200]
        elif isinstance(repo_data, str): repo = repo_data[:200]
        homepage = (pkg.get("homepage") or "")[:200]

        entry = {"name": name, "slug": slug, "registry": "npm",
                "version": latest, "description": desc,
                "author": author[:100], "license": str(license_val or "")[:100],
                "downloads": 0, "stars": 0,
                "last_updated": (pkg.get("time", {}).get("modified") or "")[:19],
                "repository_url": repo, "homepage_url": homepage,
                "dependencies_count": len(version_data.get("dependencies", {})) if version_data else 0,
                "raw_data": json.dumps({"keywords": (pkg.get("keywords") or [])[:10]})}
        entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)

        try:
            session.execute(text("""INSERT INTO software_registry
                (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                 repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                 :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                ON CONFLICT (registry,slug) DO NOTHING
            """), entry)
            new += 1; seen.add(slug)
        except Exception:
            session.rollback()
        total += 1

        if new % 2000 == 0 and new > 0:
            session.commit()
            logger.info(f"  {total} processed, {new} new")
        time.sleep(0.1)  # 10 req/sec

    session.commit(); session.close()
    logger.info(f"npm bulk complete: {total} processed, {new} NEW")
    return new


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 100000)
