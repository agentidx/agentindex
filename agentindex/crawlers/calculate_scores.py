#!/usr/bin/env python3
"""
Daily Trust Score Calculator — recalculates scores for all enriched entities.
Run daily at 07:00 via LaunchAgent.

python3 -m agentindex.crawlers.calculate_scores
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("calculate_scores")


def grade_from_score(total):
    if total >= 90: return "A+"
    if total >= 85: return "A"
    if total >= 80: return "A-"
    if total >= 75: return "B+"
    if total >= 70: return "B"
    if total >= 65: return "B-"
    if total >= 60: return "C+"
    if total >= 55: return "C"
    if total >= 50: return "C-"
    if total >= 40: return "D"
    return "F"


def calc_package(r):
    """Score for npm/pypi/crates/nuget/go/gems/packagist/homebrew."""
    dl = r["weekly_downloads"] or r["downloads"] or 0
    cve = r["cve_count"] or 0
    cve_crit = r["cve_critical"] or 0
    rels = r["release_count"] or 0
    maint_count = r["maintainer_count"] or 0
    lic = (r["license"] or "").upper()
    desc = r["description"] or ""
    has_types = r["has_types"]
    deprecated = r["deprecated"]

    if deprecated:
        return {"score": 10, "grade": "F", "security": 10, "maintenance": 10,
                "popularity": 0, "community": 10, "quality": 10}

    security = max(5, 90 - min(cve * 10, 40) - cve_crit * 15)
    maintenance = min(100, 50 + min(rels, 50))
    popularity = (100 if dl > 10_000_000 else 90 if dl > 1_000_000 else
                  75 if dl > 100_000 else 60 if dl > 10_000 else
                  45 if dl > 1_000 else 30 if dl > 100 else 15 if dl > 0 else 0)
    community = 35 + min(maint_count * 5, 45)
    quality = 30
    if any(k in lic for k in ["MIT", "BSD", "APACHE", "ISC", "0BSD"]):
        quality += 25
    elif lic:
        quality += 10
    if has_types:
        quality += 15
    if len(desc) > 30:
        quality += 10
    quality = min(100, quality)

    total = round(security * 0.25 + maintenance * 0.25 + popularity * 0.15 +
                  community * 0.15 + quality * 0.20, 1)
    return {"score": total, "grade": grade_from_score(total),
            "security": round(security, 1), "maintenance": round(maintenance, 1),
            "popularity": round(popularity, 1), "community": round(community, 1),
            "quality": round(quality, 1)}


def calc_app(r):
    """Score for iOS/Android apps."""
    dl = r["downloads"] or 0
    desc = r["description"] or ""
    deprecated = r["deprecated"]

    if deprecated:
        return {"score": 10, "grade": "F", "security": 10, "maintenance": 10,
                "popularity": 0, "community": 10, "quality": 10}

    security = 70  # default for apps from official stores
    maintenance = 60
    popularity = (100 if dl > 1_000_000_000 else 95 if dl > 100_000_000 else
                  85 if dl > 10_000_000 else 75 if dl > 1_000_000 else
                  60 if dl > 100_000 else 45 if dl > 10_000 else 30 if dl > 0 else 15)
    community = 50
    quality = 50 if len(desc) > 50 else 30

    total = round(security * 0.25 + maintenance * 0.20 + popularity * 0.20 +
                  community * 0.15 + quality * 0.20, 1)
    return {"score": total, "grade": grade_from_score(total),
            "security": round(security, 1), "maintenance": round(maintenance, 1),
            "popularity": round(popularity, 1), "community": round(community, 1),
            "quality": round(quality, 1)}


def calc_vpn(r):
    """Score for VPN services — curated, generally high quality."""
    dl = r["downloads"] or 0
    desc = r["description"] or ""
    score = r["trust_score"] or 70  # VPNs are curated, keep existing score
    return {"score": score, "grade": grade_from_score(score),
            "security": 80, "maintenance": 75, "popularity": min(100, dl // 100000),
            "community": 60, "quality": 70}


PACKAGE_REGS = {"npm", "pypi", "crates", "nuget", "go", "gems", "packagist", "homebrew"}
APP_REGS = {"ios", "android", "steam"}
VPN_REGS = {"vpn"}


def main():
    session = get_session()
    try:
        session.execute(text("SET statement_timeout = '10s'"))
        rows = session.execute(text("""
            SELECT id, registry, downloads, weekly_downloads, cve_count, cve_critical,
                   release_count, maintainer_count, license, description, has_types,
                   deprecated, trust_score
            FROM software_registry
            WHERE enriched_at IS NOT NULL
            ORDER BY registry, COALESCE(downloads, 0) DESC
        """)).fetchall()
        session.execute(text("SET statement_timeout = '10s'"))

        cols = ["id", "registry", "downloads", "weekly_downloads", "cve_count", "cve_critical",
                "release_count", "maintainer_count", "license", "description", "has_types",
                "deprecated", "trust_score"]

        total = len(rows)
        log.info(f"Calculating scores for {total} enriched entities")
        updated = 0

        for i, row in enumerate(rows):
            r = dict(zip(cols, row))
            reg = r["registry"]

            if reg in PACKAGE_REGS:
                scores = calc_package(r)
            elif reg in APP_REGS:
                scores = calc_app(r)
            elif reg in VPN_REGS:
                scores = calc_vpn(r)
            else:
                scores = calc_package(r)  # fallback

            try:
                session.execute(text("""
                    UPDATE software_registry SET
                        trust_score = :s, trust_grade = :g,
                        security_score = :sec, maintenance_score = :m,
                        popularity_score = :p, community_score = :c, quality_score = :q
                    WHERE id = :id
                """), {
                    "id": str(r["id"]), "s": scores["score"], "g": scores["grade"],
                    "sec": scores["security"], "m": scores["maintenance"],
                    "p": scores["popularity"], "c": scores["community"], "q": scores["quality"],
                })
                updated += 1
            except Exception:
                session.rollback()

            if (i + 1) % 1000 == 0:
                session.commit()
                log.info(f"Progress: {updated}/{total}")

        session.commit()
        log.info(f"Score calculation complete: {updated}/{total} updated")
    except Exception as e:
        log.error(f"Fatal: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
