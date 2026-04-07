#!/usr/bin/env python3
"""
PyPI Enrichment Pipeline — fetch downloads, metadata for all PyPI packages.
Run: python3 -m agentindex.crawlers.pypi_enrichment [limit]
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("pypi_enrichment")

PYPI_API = "https://pypi.org/pypi"
PYPISTATS = "https://pypistats.org/api/packages"
BATCH_SIZE = 50
RATE_LIMIT = 0.1  # 100ms between requests


def enrich_one(session, pkg_id, name):
    """Enrich a single PyPI package."""
    try:
        resp = requests.get(f"{PYPI_API}/{name}/json", timeout=10)
        if resp.status_code == 404:
            session.execute(text(
                "UPDATE software_registry SET enriched_at = NOW(), deprecated = true WHERE id = :id"
            ), {"id": str(pkg_id)})
            return True
        if resp.status_code != 200:
            return False

        data = resp.json()
        info = data.get("info", {})

        description = (info.get("summary") or "")[:500]
        author = info.get("author") or info.get("maintainer") or ""
        license_str = (info.get("license") or "")[:100]
        repo_url = info.get("project_urls", {}).get("Source") or info.get("project_urls", {}).get("Repository") or info.get("home_page") or ""
        if repo_url and not repo_url.startswith("http"):
            repo_url = ""
        version = info.get("version") or ""
        requires_python = info.get("requires_python") or ""

        # Release count
        releases = data.get("releases", {})
        release_count = len(releases)

        # Dependencies
        requires_dist = info.get("requires_dist") or []
        dep_count = len(requires_dist)

        # First published
        first_published = None
        if releases:
            for ver_files in releases.values():
                for f in ver_files:
                    upload = f.get("upload_time")
                    if upload:
                        try:
                            dt = datetime.fromisoformat(upload)
                            if first_published is None or dt < first_published:
                                first_published = dt
                        except Exception:
                            pass
                    break  # only check first file per version
                break

        # Weekly downloads from pypistats
        weekly_downloads = 0
        try:
            dl_resp = requests.get(f"{PYPISTATS}/{name}/recent", timeout=5,
                                   headers={"User-Agent": "nerq.ai trust engine"})
            if dl_resp.status_code == 200:
                dl_data = dl_resp.json()
                weekly_downloads = dl_data.get("data", {}).get("last_week", 0)
        except Exception:
            pass

        session.execute(text("""
            UPDATE software_registry SET
                downloads = GREATEST(COALESCE(downloads, 0), :dl),
                weekly_downloads = :weekly_dl,
                description = COALESCE(NULLIF(:desc, ''), description),
                author = COALESCE(NULLIF(:author, ''), author),
                license = COALESCE(NULLIF(:license, ''), license),
                repository_url = COALESCE(NULLIF(:repo, ''), repository_url),
                dependencies_count = :dep_count,
                release_count = :rel_count,
                latest_version = :ver,
                first_published = COALESCE(:fp, first_published),
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id),
            "dl": weekly_downloads,
            "weekly_dl": weekly_downloads,
            "desc": description,
            "author": author[:200] if author else "",
            "license": license_str,
            "repo": repo_url[:500] if repo_url else "",
            "dep_count": dep_count,
            "rel_count": release_count,
            "ver": version[:50] if version else None,
            "fp": first_published,
        })
        return True

    except requests.exceptions.Timeout:
        return False
    except Exception as e:
        log.warning(f"Error: {name}: {e}")
        return False


def calculate_pypi_trust(session, pkg_id):
    """Calculate trust score for PyPI package."""
    row = session.execute(text("""
        SELECT weekly_downloads, downloads, release_count, dependencies_count,
               license, description, deprecated, cve_count, cve_critical
        FROM software_registry WHERE id = :id
    """), {"id": str(pkg_id)}).fetchone()
    if not row:
        return

    dl = row[0] or row[1] or 0
    release_count = row[2] or 0
    license_str = (row[4] or "").upper()
    description = row[5] or ""
    deprecated = row[6]
    cve_count = row[7] or 0

    if deprecated:
        session.execute(text(
            "UPDATE software_registry SET trust_score = 10, trust_grade = 'F' WHERE id = :id"
        ), {"id": str(pkg_id)})
        return

    security = max(5, 90 - min(cve_count * 10, 40))
    maintenance = 50
    if release_count > 50:
        maintenance = 85
    elif release_count > 20:
        maintenance = 70
    elif release_count > 5:
        maintenance = 50

    popularity = 0
    if dl > 10_000_000:
        popularity = 100
    elif dl > 1_000_000:
        popularity = 90
    elif dl > 100_000:
        popularity = 75
    elif dl > 10_000:
        popularity = 60
    elif dl > 1_000:
        popularity = 45
    elif dl > 100:
        popularity = 30
    elif dl > 0:
        popularity = 15

    community = 35
    quality = 30
    if license_str in ("MIT", "BSD-3-CLAUSE", "BSD-2-CLAUSE", "APACHE-2.0", "ISC", "APACHE 2.0"):
        quality += 25
    elif "MIT" in license_str or "BSD" in license_str or "APACHE" in license_str:
        quality += 20
    elif license_str:
        quality += 10
    if len(description) > 30:
        quality += 10
    quality = min(100, quality)

    total = round(security * 0.25 + maintenance * 0.25 + popularity * 0.15 + community * 0.15 + quality * 0.20, 1)
    grade = "A+" if total >= 90 else "A" if total >= 85 else "A-" if total >= 80 else "B+" if total >= 75 else "B" if total >= 70 else "B-" if total >= 65 else "C+" if total >= 60 else "C" if total >= 55 else "C-" if total >= 50 else "D" if total >= 40 else "F"

    session.execute(text("""
        UPDATE software_registry SET
            trust_score = :score, trust_grade = :grade,
            security_score = :sec, maintenance_score = :maint,
            popularity_score = :pop, community_score = :comm, quality_score = :qual
        WHERE id = :id
    """), {
        "id": str(pkg_id), "score": total, "grade": grade,
        "sec": round(security, 1), "maint": round(maintenance, 1),
        "pop": round(popularity, 1), "comm": round(community, 1), "qual": round(quality, 1),
    })


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50000

    session = get_session()
    try:
        session.execute(text("SET statement_timeout = '10s'"))
        rows = session.execute(text("""
            SELECT id, name FROM software_registry
            WHERE registry = 'pypi' AND enriched_at IS NULL
            ORDER BY COALESCE(downloads, 0) DESC, name ASC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
        session.execute(text("SET statement_timeout = '10s'"))

        total = len(rows)
        log.info(f"PyPI enrichment: {total} packages (limit={limit})")

        done = 0
        for i, pkg in enumerate(rows):
            if enrich_one(session, pkg[0], pkg[1]):
                calculate_pypi_trust(session, pkg[0])
                done += 1

            if (i + 1) % BATCH_SIZE == 0:
                session.commit()
                if (i + 1) % 500 == 0:
                    log.info(f"Progress: {done}/{total} ({done * 100 // max(1, total)}%)")

            time.sleep(RATE_LIMIT)

        session.commit()
        log.info(f"PyPI enrichment complete: {done}/{total}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
