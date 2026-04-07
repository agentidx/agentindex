#!/usr/bin/env python3
"""Homebrew Crawler — one JSON file with ALL formulae."""
import json, logging, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("homebrew_crawler")


def crawl(limit=10000):
    logger.info(f"Homebrew crawl (limit={limit})")

    try:
        r = http.get("https://formulae.brew.sh/api/formula.json", timeout=30)
        if r.status_code != 200:
            logger.error(f"API error: {r.status_code}"); return 0
        formulae = r.json()
        logger.info(f"  Got {len(formulae)} formulae from Homebrew")
    except Exception as e:
        logger.error(f"Fetch error: {e}"); return 0

    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='homebrew'")).fetchall()
    seen = {r[0] for r in rows}
    total = 0; new = 0

    for f in formulae[:limit]:
        name = f.get("name") or f.get("full_name", "")
        if not name: continue
        slug = name.lower().replace("@", "-at-")

        if slug in seen:
            total += 1; continue
        seen.add(slug)

        desc = f.get("desc") or ""
        homepage = f.get("homepage") or ""
        license_val = f.get("license") or ""
        versions = f.get("versions", {})
        stable = versions.get("stable") if isinstance(versions, dict) else None

        # Homebrew-specific trust: installed count from analytics
        installed = f.get("analytics", {}).get("install_on_request", {}).get("30d", {})
        install_count = sum(installed.values()) if isinstance(installed, dict) else 0

        score = 0
        if install_count >= 100000: score += 30
        elif install_count >= 10000: score += 25
        elif install_count >= 1000: score += 18
        elif install_count > 0: score += 10
        if license_val: score += 15
        if desc and len(desc) > 20: score += 10
        if homepage: score += 5
        if stable: score += 10
        score += 15  # In official Homebrew = trusted
        score = max(0, min(100, score))
        grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"

        entry = {"name": name, "slug": slug, "registry": "homebrew",
                "version": stable, "description": desc[:500],
                "author": "", "license": str(license_val)[:100],
                "downloads": install_count, "stars": 0,
                "last_updated": None, "repository_url": "",
                "homepage_url": homepage,
                "dependencies_count": len(f.get("dependencies", [])),
                "trust_score": round(score, 1), "trust_grade": grade,
                "raw_data": json.dumps({"deps": f.get("dependencies", [])[:10],
                                       "installs_30d": install_count})}
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

    session.commit(); session.close()
    logger.info(f"Homebrew complete: {total} processed, {new} NEW")
    return new

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 10000)
