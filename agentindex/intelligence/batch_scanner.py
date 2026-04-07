#!/usr/bin/env python3
"""
Batch Entity Scanner
======================
Scans all entities from data/entities/*.json, rates them, stores results.
Run: python3 agentindex/intelligence/batch_scanner.py [--type saas|companies|government|universities]
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agentindex.db.models import get_session
from agentindex.intelligence.rating_engine import rate_entity, score_to_rating
from agentindex.intelligence.org_scanner import scan_github_org
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/batch-scanner.log")])
logger = logging.getLogger("nerq.batch_scanner")

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "entities"

ENTITY_TYPE_MAP = {
    "saas.json": "saas",
    "companies.json": "company",
    "government.json": "government",
    "universities.json": "university",
}


def lookup_tool_trust(tool_name: str) -> dict:
    """Look up a tool's trust score in our database."""
    session = get_session()
    try:
        row = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, stars, downloads, category
            FROM entity_lookup
            WHERE name_lower LIKE :pattern AND is_active = true
            ORDER BY COALESCE(stars, 0) DESC LIMIT 1
        """), {"pattern": f"%{tool_name.lower()}%"}).fetchone()
        if row:
            return {
                "name": tool_name, "db_name": row[0],
                "trust_score": float(row[1]) if row[1] else 50,
                "grade": row[2] or "D", "stars": row[3] or 0,
                "downloads": row[4] or 0, "category": row[5] or "",
            }
    finally:
        session.close()
    return {"name": tool_name, "trust_score": 50, "grade": "D", "stars": 0, "downloads": 0, "category": ""}


def scan_and_rate_entity(entity: dict, entity_type: str) -> dict | None:
    """Scan one entity and store the rating."""
    name = entity.get("name", "Unknown")
    slug = entity.get("slug", "")
    github_org = entity.get("github_org")

    logger.info(f"Scanning {entity_type}: {name} (github: {github_org})")

    # Scan GitHub org if available
    scan_result = None
    if github_org:
        try:
            scan_result = scan_github_org(github_org, max_repos=30)
        except Exception as e:
            logger.warning(f"GitHub scan failed for {name}: {e}")

    # Build tools list with trust scores
    tools = []
    ai_tool_names = scan_result.get("ai_tools_found", []) if scan_result else []

    # Also add known AI features from config
    for feature in entity.get("ai_features", []):
        feature_lower = feature.lower().replace(" ", "-")
        if feature_lower not in [t.lower() for t in ai_tool_names]:
            ai_tool_names.append(feature_lower)

    for tool_name in ai_tool_names:
        trust_data = lookup_tool_trust(tool_name)
        tools.append(trust_data)

    # Rate the entity
    metadata = {
        "entity_type": entity_type,
        "github_org": github_org,
        "repos_scanned": scan_result.get("repos_scanned", 0) if scan_result else 0,
        "total_deps": scan_result.get("total_deps", 0) if scan_result else 0,
    }

    rating_result = rate_entity(tools, metadata)

    # Store in database
    session = get_session()
    try:
        session.execute(text("""
            INSERT INTO entity_ratings
                (entity_type, entity_name, entity_slug, display_name, github_org,
                 website, industry, country, ticker, stock_index,
                 rating, score, tools_found, dependencies_total,
                 critical_issues, health_warnings,
                 tool_breakdown, risk_factors, predictions, compliance_signals, scan_sources)
            VALUES
                (:etype, :ename, :eslug, :dname, :ghorg,
                 :website, :industry, :country, :ticker, :sindex,
                 :rating, :score, :tools, :deps,
                 :critical, :warnings,
                 CAST(:breakdown AS jsonb), CAST(:risks AS jsonb),
                 CAST(:preds AS jsonb), CAST(:compliance AS jsonb), CAST(:sources AS jsonb))
            ON CONFLICT (entity_type, entity_slug) DO UPDATE SET
                rating = EXCLUDED.rating,
                score = EXCLUDED.score,
                tools_found = EXCLUDED.tools_found,
                dependencies_total = EXCLUDED.dependencies_total,
                critical_issues = EXCLUDED.critical_issues,
                health_warnings = EXCLUDED.health_warnings,
                tool_breakdown = EXCLUDED.tool_breakdown,
                risk_factors = EXCLUDED.risk_factors,
                predictions = EXCLUDED.predictions,
                scan_sources = EXCLUDED.scan_sources,
                updated_at = NOW()
        """), {
            "etype": entity_type, "ename": name, "eslug": slug,
            "dname": entity.get("name"), "ghorg": github_org,
            "website": entity.get("website"), "industry": entity.get("industry"),
            "country": entity.get("country"), "ticker": entity.get("ticker"),
            "sindex": entity.get("index"),
            "rating": rating_result["rating"], "score": rating_result["score"],
            "tools": rating_result["tools_analyzed"],
            "deps": rating_result["dependencies_total"],
            "critical": rating_result["critical_issues"],
            "warnings": rating_result["health_warnings"],
            "breakdown": json.dumps(rating_result["tool_breakdown"]),
            "risks": json.dumps(rating_result["risk_factors"]),
            "preds": json.dumps(rating_result["predictions"]),
            "compliance": json.dumps(rating_result.get("compliance_signals", {})),
            "sources": json.dumps({
                "github_org": github_org,
                "repos_scanned": scan_result.get("repos_scanned", 0) if scan_result else 0,
                "dep_files": scan_result.get("dep_files_found", 0) if scan_result else 0,
                "scanned_at": datetime.utcnow().isoformat(),
            }),
        })
        session.commit()
        logger.info(f"  Rated {name}: {rating_result['rating']} ({rating_result['score']:.0f}/100), {rating_result['tools_analyzed']} AI tools")
        return rating_result
    except Exception as e:
        logger.error(f"  Failed to store rating for {name}: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def scan_all(entity_type_filter: str = None):
    """Scan all entities from config files."""
    start = time.time()
    total_scanned = 0
    total_rated = 0
    ratings = {"AAA": 0, "AA": 0, "A": 0, "BBB": 0, "BB": 0, "B": 0, "CCC": 0, "CC": 0, "C": 0}

    for filename, etype in ENTITY_TYPE_MAP.items():
        if entity_type_filter and etype != entity_type_filter:
            continue

        filepath = DATA_DIR / filename
        if not filepath.exists():
            logger.warning(f"Config not found: {filepath}")
            continue

        with open(filepath) as f:
            entities = json.load(f)

        logger.info(f"=== Scanning {len(entities)} {etype} entities from {filename} ===")

        for entity in entities:
            result = scan_and_rate_entity(entity, etype)
            total_scanned += 1
            if result:
                total_rated += 1
                r = result["rating"]
                if r in ratings:
                    ratings[r] += 1

            # Rate limit: pause between entities to respect GitHub API
            time.sleep(1)

    elapsed = time.time() - start
    logger.info(f"=== SCAN COMPLETE ===")
    logger.info(f"  Scanned: {total_scanned}, Rated: {total_rated}")
    logger.info(f"  Distribution: {json.dumps(ratings)}")
    logger.info(f"  Elapsed: {elapsed:.0f}s")

    return {"scanned": total_scanned, "rated": total_rated, "ratings": ratings}


if __name__ == "__main__":
    filter_type = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "--type" else None
    if "--type" in sys.argv:
        idx = sys.argv.index("--type")
        filter_type = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    result = scan_all(filter_type)
    print(json.dumps(result, indent=2))
