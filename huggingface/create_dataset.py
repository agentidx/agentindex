#!/usr/bin/env python3
"""
HuggingFace Dataset Creator
=============================
Exports top 10,000 agents as CSV and JSON for HuggingFace upload.

Usage:
    python huggingface/create_dataset.py
"""

import csv
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.sql import text

OUTPUT_DIR = Path(__file__).parent
SQLITE_DB = Path(__file__).parent.parent / "agentindex" / "crypto" / "crypto_trust.db"


def export_dataset(limit=10000):
    from agentindex.db.models import get_session
    session = get_session()

    rows = session.execute(text("""
        SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
               trust_grade, category, license, source, stars, forks, downloads,
               last_source_update, frameworks, language, description
        FROM agents
        WHERE is_active = true
          AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
        ORDER BY COALESCE(trust_score_v2, trust_score) DESC
        LIMIT :lim
    """), {"lim": limit}).fetchall()

    session.close()

    # Load enrichment data from SQLite
    cve_counts = {}
    license_cats = {}
    framework_map = {}
    npm_downloads = {}
    try:
        conn = sqlite3.connect(str(SQLITE_DB))
        for r in conn.execute("SELECT agent_name, COUNT(*) FROM agent_vulnerabilities GROUP BY agent_name"):
            cve_counts[r[0]] = r[1]
        for r in conn.execute("SELECT agent_name, license_category FROM agent_licenses"):
            license_cats[r[0]] = r[1]
        for r in conn.execute("SELECT agent_name, GROUP_CONCAT(framework, ', ') FROM agent_frameworks GROUP BY agent_name"):
            framework_map[r[0]] = r[1]
        for r in conn.execute("SELECT agent_id, weekly_downloads FROM package_downloads WHERE registry = 'npm'"):
            npm_downloads[r[0]] = r[1]
        conn.close()
    except Exception:
        pass

    # Build dataset
    records = []
    for r in rows:
        d = dict(r._mapping)
        name = d["name"]
        records.append({
            "name": name,
            "trust_score": round(float(d["trust_score"]), 1) if d["trust_score"] else None,
            "grade": d["trust_grade"],
            "category": d.get("category"),
            "known_cves": cve_counts.get(name, 0),
            "license": d.get("license"),
            "license_category": license_cats.get(name),
            "frameworks": framework_map.get(name, ""),
            "npm_weekly_downloads": npm_downloads.get(name, 0),
            "github_stars": d.get("stars", 0),
            "github_forks": d.get("forks", 0),
            "language": d.get("language"),
            "source": d.get("source"),
            "last_updated": str(d.get("last_source_update", ""))[:10] if d.get("last_source_update") else None,
            "description": (d.get("description") or "")[:300],
        })

    # Save CSV
    csv_path = OUTPUT_DIR / "agents_trust_scores.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)

    # Save JSON
    json_path = OUTPUT_DIR / "agents_trust_scores.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str)

    print(f"Exported {len(records)} agents")
    print(f"  CSV: {csv_path} ({csv_path.stat().st_size / 1024:.0f} KB)")
    print(f"  JSON: {json_path} ({json_path.stat().st_size / 1024:.0f} KB)")

    # Stats
    grades = {}
    for r in records:
        g = r["grade"] or "None"
        grades[g] = grades.get(g, 0) + 1

    with_cves = sum(1 for r in records if r["known_cves"] > 0)
    avg_score = sum(r["trust_score"] for r in records if r["trust_score"]) / len(records)
    print(f"  Average trust score: {avg_score:.1f}")
    print(f"  With known CVEs: {with_cves}")
    print(f"  Grade distribution: {dict(sorted(grades.items()))}")

    return len(records)


if __name__ == "__main__":
    os.chdir(Path(__file__).parent.parent)
    export_dataset()
