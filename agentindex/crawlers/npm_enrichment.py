#!/usr/bin/env python3
"""
npm Enrichment Pipeline — fetch downloads, metadata, repo info for all npm packages.

Prioritizes top packages first (by existing trust_score, then alphabetical).
Uses npm registry API + downloads API.

Run: python3 -m agentindex.crawlers.npm_enrichment [limit]
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
log = logging.getLogger("npm_enrichment")

REGISTRY = "https://registry.npmjs.org"
DOWNLOADS = "https://api.npmjs.org/downloads/point/last-week"
BATCH_SIZE = 100  # commit every N packages
RATE_LIMIT = 0.05  # 50ms between requests (~20 req/s)


def enrich_batch(session, packages):
    """Enrich a batch of npm packages."""
    enriched = 0
    for pkg in packages:
        pkg_id = pkg[0]
        name = pkg[1]

        try:
            # 1. Registry metadata
            resp = requests.get(f"{REGISTRY}/{name}", timeout=10)
            if resp.status_code == 404:
                # Package deleted/unpublished
                session.execute(text(
                    "UPDATE software_registry SET enriched_at = NOW(), deprecated = true WHERE id = :id"
                ), {"id": str(pkg_id)})
                continue
            if resp.status_code != 200:
                time.sleep(0.2)
                continue

            data = resp.json()

            # Extract metadata
            dist_tags = data.get("dist-tags", {})
            latest_version = dist_tags.get("latest", "")
            latest_data = data.get("versions", {}).get(latest_version, {})

            # Repository URL
            repo = data.get("repository", {})
            repo_url = None
            if isinstance(repo, dict):
                repo_url = repo.get("url", "")
            elif isinstance(repo, str):
                repo_url = repo
            if repo_url:
                repo_url = repo_url.replace("git+", "").replace("git://", "https://").replace(".git", "")
                if not repo_url.startswith("http"):
                    repo_url = None

            # License
            license_info = data.get("license", "")
            if isinstance(license_info, dict):
                license_info = license_info.get("type", "")

            # Maintainers
            maintainers = data.get("maintainers", [])
            maintainer_count = len(maintainers)
            first_maintainer = maintainers[0].get("name", "") if maintainers else ""

            # Description
            description = (data.get("description") or "")[:500]

            # Dependencies
            deps = latest_data.get("dependencies", {})
            dep_count = len(deps) if deps else 0

            # TypeScript types
            has_types = bool(latest_data.get("types") or latest_data.get("typings"))

            # Release count
            release_count = len(data.get("versions", {}))

            # Creation date
            time_data = data.get("time", {})
            created = time_data.get("created")
            first_published = None
            if created:
                try:
                    first_published = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except Exception:
                    pass

            # 2. Weekly downloads
            weekly_downloads = 0
            try:
                dl_resp = requests.get(f"{DOWNLOADS}/{name}", timeout=5)
                if dl_resp.status_code == 200:
                    dl_data = dl_resp.json()
                    weekly_downloads = dl_data.get("downloads", 0)
            except Exception:
                pass

            # 3. Update database
            session.execute(text("""
                UPDATE software_registry SET
                    downloads = CASE WHEN COALESCE(downloads, 0) > :weekly_dl THEN downloads ELSE :weekly_dl END,
                    weekly_downloads = :weekly_dl,
                    description = COALESCE(NULLIF(:desc, ''), description),
                    author = COALESCE(NULLIF(:author, ''), author),
                    license = COALESCE(NULLIF(:license, ''), license),
                    repository_url = COALESCE(:repo_url, repository_url),
                    maintainer_count = :maintainer_count,
                    dependencies_count = :dep_count,
                    has_types = :has_types,
                    release_count = :release_count,
                    latest_version = :latest_ver,
                    first_published = COALESCE(:first_pub, first_published),
                    enriched_at = NOW()
                WHERE id = :id
            """), {
                "id": str(pkg_id),
                "weekly_dl": weekly_downloads,
                "desc": description,
                "author": first_maintainer,
                "license": str(license_info)[:100] if license_info else "",
                "repo_url": repo_url,
                "maintainer_count": maintainer_count,
                "dep_count": dep_count,
                "has_types": has_types,
                "release_count": release_count,
                "latest_ver": latest_version[:50] if latest_version else None,
                "first_pub": first_published,
            })
            enriched += 1

        except requests.exceptions.Timeout:
            log.warning(f"Timeout: {name}")
            try:
                session.rollback()
            except Exception:
                pass
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"Error enriching {name}: {e}")
            try:
                session.rollback()
            except Exception:
                pass

        time.sleep(RATE_LIMIT)

    return enriched


def calculate_npm_trust(session, pkg_id):
    """Calculate 5-dimension trust score for an enriched npm package."""
    row = session.execute(text("""
        SELECT weekly_downloads, downloads, stars, forks, open_issues,
               last_commit, release_count, maintainer_count, contributors,
               cve_count, cve_critical, openssf_score,
               license, has_types, description, dependencies_count, deprecated
        FROM software_registry WHERE id = :id
    """), {"id": str(pkg_id)}).fetchone()
    if not row:
        return

    dl = row[0] or row[1] or 0
    stars = row[2] or 0
    release_count = row[6] or 0
    maintainer_count = row[7] or 0
    cve_count = row[9] or 0
    cve_critical = row[10] or 0
    license_str = (row[12] or "").upper()
    has_types = row[13]
    description = row[14] or ""
    deprecated = row[16]

    if deprecated:
        session.execute(text(
            "UPDATE software_registry SET trust_score = 10, trust_grade = 'F' WHERE id = :id"
        ), {"id": str(pkg_id)})
        return

    # Security (25%)
    security = 90
    if cve_count > 0:
        security -= min(cve_count * 10, 40)
    if cve_critical > 0:
        security -= cve_critical * 15
    security = max(5, min(100, security))

    # Maintenance (25%)
    maintenance = 50
    if release_count > 100:
        maintenance = 90
    elif release_count > 50:
        maintenance = 80
    elif release_count > 20:
        maintenance = 65
    elif release_count > 5:
        maintenance = 50
    elif release_count > 1:
        maintenance = 35

    # Popularity (15%)
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
    if stars > 10000:
        popularity = min(100, popularity + 15)
    elif stars > 1000:
        popularity = min(100, popularity + 10)

    # Community (15%)
    community = 30
    if maintainer_count > 10:
        community = 80
    elif maintainer_count > 3:
        community = 60
    elif maintainer_count > 1:
        community = 45

    # Quality (20%)
    quality = 30
    if license_str in ("MIT", "ISC", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "APACHE-2.0", "0BSD"):
        quality += 25
    elif license_str:
        quality += 10
    if has_types:
        quality += 15
    if len(description) > 30:
        quality += 10
    quality = min(100, quality)

    total = (security * 0.25 + maintenance * 0.25 +
             popularity * 0.15 + community * 0.15 + quality * 0.20)
    total = round(total, 1)

    # Grade
    if total >= 90:
        grade = "A+"
    elif total >= 85:
        grade = "A"
    elif total >= 80:
        grade = "A-"
    elif total >= 75:
        grade = "B+"
    elif total >= 70:
        grade = "B"
    elif total >= 65:
        grade = "B-"
    elif total >= 60:
        grade = "C+"
    elif total >= 55:
        grade = "C"
    elif total >= 50:
        grade = "C-"
    elif total >= 40:
        grade = "D"
    else:
        grade = "F"

    session.execute(text("""
        UPDATE software_registry SET
            trust_score = :score, trust_grade = :grade,
            security_score = :sec, maintenance_score = :maint,
            popularity_score = :pop, community_score = :comm, quality_score = :qual
        WHERE id = :id
    """), {
        "id": str(pkg_id),
        "score": total, "grade": grade,
        "sec": round(security, 1), "maint": round(maintenance, 1),
        "pop": round(popularity, 1), "comm": round(community, 1), "qual": round(quality, 1),
    })


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100000

    session = get_session()
    try:
        # Set longer timeout for bulk queries
        session.execute(text("SET statement_timeout = '10s'"))

        # Get unenriched npm packages (use partial index, no expensive sort)
        rows = session.execute(text("""
            SELECT id, name FROM software_registry
            WHERE registry = 'npm' AND enriched_at IS NULL
            ORDER BY COALESCE(downloads, 0) DESC, name ASC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
        session.execute(text("SET statement_timeout = '10s'"))

        total = len(rows)
        log.info(f"npm enrichment: {total} packages to process (limit={limit})")

        done = 0
        for i in range(0, total, BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            n = enrich_batch(session, batch)
            done += n

            session.commit()

            # Calculate trust scores in bulk (much faster than per-entity)
            try:
                pkg_ids = [str(pkg[0]) for pkg in batch]
                for pid in pkg_ids:
                    try:
                        calculate_npm_trust(session, pid)
                    except Exception:
                        pass
                session.commit()
            except Exception:
                session.rollback()

            if (i // BATCH_SIZE) % 10 == 0:
                log.info(f"Progress: {done}/{total} enriched ({done * 100 // max(1, total)}%)")

        session.commit()
        log.info(f"npm enrichment complete: {done}/{total} enriched")

    finally:
        session.close()


if __name__ == "__main__":
    main()
