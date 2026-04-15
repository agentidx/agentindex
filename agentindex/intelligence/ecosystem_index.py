#!/usr/bin/env python3
"""
Ecosystem Trust Index — daily calculation of the AI Agent Ecosystem health.

Like a stock market index but for AI agent trust. Calculates:
- Overall Trust Index (weighted average across all graded agents)
- Sub-indices: Security, Maintenance, License, Framework
- Category indices: by source, by category
- Grade distribution shifts

Runs daily via LaunchAgent com.nerq.ecosystem-index at 09:45.
Results stored in SQLite ecosystem_index table.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

logger = logging.getLogger(__name__)

SQLITE_PATH = Path(__file__).resolve().parent.parent / "crypto" / "crypto_trust.db"


def _pg_conn():
    from agentindex.db_config import get_write_conn
    return get_write_conn()


def _ensure_table(sconn: sqlite3.Connection):
    sconn.execute("""
        CREATE TABLE IF NOT EXISTS ecosystem_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            index_name TEXT NOT NULL,
            value REAL NOT NULL,
            change_1d REAL,
            change_7d REAL,
            change_30d REAL,
            components TEXT,
            metadata TEXT,
            calculated_at TEXT NOT NULL,
            UNIQUE(date, index_name)
        )
    """)
    sconn.commit()


def _get_previous(sconn, index_name, days_ago):
    """Get index value from N days ago."""
    row = sconn.execute(
        "SELECT value FROM ecosystem_index WHERE index_name = ? ORDER BY date DESC LIMIT 1 OFFSET ?",
        (index_name, days_ago - 1)
    ).fetchone()
    return row[0] if row else None


def calculate_overall_index(pgconn) -> dict:
    """
    Calculate the overall Ecosystem Trust Index.

    Weighting: npm downloads (if available) > GitHub stars > equal weight.
    This gives more influence to agents that are actually used.
    """
    cur = pgconn.cursor()

    cur.execute("""
        WITH scored AS (
            SELECT
                COALESCE(trust_score_v2, trust_score) AS ts,
                COALESCE(stars, 0) AS s,
                COALESCE(downloads, 0) AS dl
            FROM entity_lookup
            WHERE is_active = true
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
        )
        SELECT
            SUM(ts * CASE
                WHEN dl > 0 THEN LEAST(dl, 1000000)
                WHEN s > 0 THEN LEAST(s, 100000)
                ELSE 1
            END) / NULLIF(SUM(CASE
                WHEN dl > 0 THEN LEAST(dl, 1000000)
                WHEN s > 0 THEN LEAST(s, 100000)
                ELSE 1
            END), 0) AS weighted_avg,
            AVG(ts) AS simple_avg,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ts) AS median,
            COUNT(*) AS total,
            STDDEV(ts) AS stddev
        FROM scored
    """)
    row = cur.fetchone()
    return {
        "weighted_index": round(row[0], 2),
        "simple_avg": round(row[1], 2),
        "median": round(row[2], 2),
        "total_agents": row[3],
        "stddev": round(row[4], 2) if row[4] else 0,
    }


def calculate_grade_distribution(pgconn) -> dict:
    """Grade distribution for all active, scored agents."""
    cur = pgconn.cursor()
    cur.execute("""
        SELECT trust_grade, COUNT(*)
        FROM entity_lookup
        WHERE is_active = true AND trust_grade IS NOT NULL
        GROUP BY trust_grade
        ORDER BY COUNT(*) DESC
    """)
    dist = {r[0]: r[1] for r in cur.fetchall()}
    total = sum(dist.values())
    pcts = {k: round(v / total * 100, 2) for k, v in dist.items()}
    return {"counts": dist, "percentages": pcts, "total": total}


def calculate_source_indices(pgconn) -> dict:
    """Trust index broken down by source platform."""
    cur = pgconn.cursor()
    cur.execute("""
        SELECT source,
               COUNT(*) AS cnt,
               AVG(COALESCE(trust_score_v2, trust_score)) AS avg_score,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY COALESCE(trust_score_v2, trust_score)) AS median
        FROM entity_lookup
        WHERE is_active = true AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
        GROUP BY source
        HAVING COUNT(*) >= 100
        ORDER BY avg_score DESC
    """)
    return {
        r[0]: {"count": r[1], "avg_score": round(r[2], 1), "median": round(r[3], 1)}
        for r in cur.fetchall()
    }


def calculate_category_indices(pgconn) -> dict:
    """Trust index broken down by category."""
    cur = pgconn.cursor()
    cur.execute("""
        SELECT category,
               COUNT(*) AS cnt,
               AVG(COALESCE(trust_score_v2, trust_score)) AS avg_score
        FROM entity_lookup
        WHERE is_active = true
          AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
          AND category IS NOT NULL AND category != ''
        GROUP BY category
        HAVING COUNT(*) >= 50
        ORDER BY avg_score DESC
    """)
    return {
        r[0]: {"count": r[1], "avg_score": round(r[2], 1)}
        for r in cur.fetchall()
    }


def calculate_security_subindex(pgconn, sconn) -> dict:
    """Security sub-index: based on agents with vulnerability data."""
    cur = pgconn.cursor()

    # Overall security score average
    cur.execute("""
        SELECT AVG(security_score), COUNT(*)
        FROM entity_lookup
        WHERE is_active = true AND security_score IS NOT NULL AND security_score > 0
    """)
    row = cur.fetchone()
    avg_security = round(row[0], 1) if row[0] else 0
    agents_with_security = row[1]

    # CVE stats from SQLite
    scur = sconn.cursor()
    scur.execute("SELECT COUNT(DISTINCT agent_name), COUNT(*) FROM agent_vulnerabilities")
    vuln_row = scur.fetchone()
    agents_with_cves = vuln_row[0]
    total_cves = vuln_row[1]

    scur.execute("""
        SELECT severity, COUNT(*) FROM agent_vulnerabilities
        GROUP BY severity ORDER BY COUNT(*) DESC
    """)
    severity_dist = {r[0]: r[1] for r in scur.fetchall()}

    return {
        "index": avg_security,
        "agents_scored": agents_with_security,
        "agents_with_cves": agents_with_cves,
        "total_cves": total_cves,
        "severity_distribution": severity_dist,
    }


def calculate_maintenance_subindex(pgconn) -> dict:
    """Maintenance sub-index: activity scores and freshness."""
    cur = pgconn.cursor()

    cur.execute("""
        SELECT AVG(activity_score), COUNT(*)
        FROM entity_lookup
        WHERE is_active = true AND activity_score IS NOT NULL AND activity_score > 0
    """)
    row = cur.fetchone()
    avg_activity = round(row[0], 1) if row[0] else 0

    # Freshness: agents updated in last 30/90/365 days
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE last_source_update > NOW() - INTERVAL '30 days') AS fresh_30,
            COUNT(*) FILTER (WHERE last_source_update > NOW() - INTERVAL '90 days') AS fresh_90,
            COUNT(*) FILTER (WHERE last_source_update > NOW() - INTERVAL '365 days') AS fresh_365,
            COUNT(*) FILTER (WHERE last_source_update IS NOT NULL) AS has_date,
            COUNT(*) AS total
        FROM agents
        WHERE is_active = true AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
    """)
    fr = cur.fetchone()

    return {
        "index": avg_activity,
        "updated_30d": fr[0],
        "updated_90d": fr[1],
        "updated_365d": fr[2],
        "has_update_date": fr[3],
        "total": fr[4],
        "freshness_30d_pct": round(fr[0] / fr[4] * 100, 2) if fr[4] else 0,
    }


def calculate_license_subindex(sconn) -> dict:
    """License sub-index: based on license data coverage and permissiveness."""
    scur = sconn.cursor()

    scur.execute("SELECT COUNT(DISTINCT agent_name) FROM agent_licenses")
    total_licensed = scur.fetchone()[0]

    scur.execute("""
        SELECT license_category, COUNT(*)
        FROM agent_licenses
        GROUP BY license_category
        ORDER BY COUNT(*) DESC
    """)
    categories = {r[0]: r[1] for r in scur.fetchall()}

    scur.execute("""
        SELECT license_spdx, COUNT(*)
        FROM agent_licenses
        GROUP BY license_spdx
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    top_licenses = {r[0]: r[1] for r in scur.fetchall()}

    # Score: % with permissive licenses (MIT, Apache, BSD)
    permissive = categories.get("PERMISSIVE", 0) + categories.get("permissive", 0)
    copyleft = categories.get("COPYLEFT", 0) + categories.get("copyleft", 0) + categories.get("VIRAL", 0) + categories.get("strong_copyleft", 0)
    other = total_licensed - permissive - copyleft
    license_health = round(permissive / total_licensed * 100, 1) if total_licensed else 0

    return {
        "index": license_health,
        "total_licensed": total_licensed,
        "permissive": permissive,
        "copyleft": copyleft,
        "other": other,
        "top_licenses": top_licenses,
        "categories": categories,
    }


def calculate_framework_subindex(sconn) -> dict:
    """Framework sub-index: framework adoption and compatibility."""
    scur = sconn.cursor()

    scur.execute("SELECT COUNT(DISTINCT agent_id) FROM agent_frameworks")
    agents_with_frameworks = scur.fetchone()[0]

    scur.execute("""
        SELECT framework, COUNT(*)
        FROM agent_frameworks
        GROUP BY framework
        ORDER BY COUNT(*) DESC
        LIMIT 15
    """)
    framework_adoption = {r[0]: r[1] for r in scur.fetchall()}

    scur.execute("SELECT COUNT(DISTINCT mcp_server_id) FROM mcp_compatibility")
    mcp_agents = scur.fetchone()[0]

    return {
        "agents_with_frameworks": agents_with_frameworks,
        "mcp_compatible": mcp_agents,
        "framework_adoption": framework_adoption,
    }


def calculate_stars_trust_correlation(pgconn) -> dict:
    """Stars vs trust score correlation by bucket."""
    cur = pgconn.cursor()
    cur.execute("""
        SELECT
            CASE
                WHEN stars IS NULL OR stars = 0 THEN '0'
                WHEN stars < 100 THEN '1-99'
                WHEN stars < 1000 THEN '100-999'
                WHEN stars < 10000 THEN '1K-10K'
                WHEN stars < 100000 THEN '10K-100K'
                ELSE '100K+'
            END AS bucket,
            COUNT(*),
            AVG(COALESCE(trust_score_v2, trust_score)),
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY COALESCE(trust_score_v2, trust_score))
        FROM entity_lookup
        WHERE is_active = true AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
        GROUP BY 1
        ORDER BY MIN(COALESCE(stars, 0))
    """)
    return {
        r[0]: {"count": r[1], "avg": round(r[2], 1), "median": round(r[3], 1)}
        for r in cur.fetchall()
    }


def generate_summary(overall, grades, security, maintenance, license_idx) -> str:
    """Generate a market-open style summary."""
    idx = overall["weighted_index"]
    total = overall["total_agents"]

    # Grade letter
    if idx >= 80:
        letter = "A"
    elif idx >= 70:
        letter = "B"
    elif idx >= 60:
        letter = "C"
    elif idx >= 50:
        letter = "D"
    else:
        letter = "F"

    d_pct = grades["percentages"].get("D", 0) + grades["percentages"].get("D+", 0) + grades["percentages"].get("D-", 0)
    a_pct = grades["percentages"].get("A", 0) + grades["percentages"].get("A+", 0)

    lines = [
        f"Nerq Ecosystem Trust Index: {idx}/100 ({letter})",
        f"Tracking {total:,} AI agents and tools across GitHub, npm, PyPI, Docker Hub, and HuggingFace.",
        f"",
        f"Grade distribution: {d_pct:.1f}% D-grade, {a_pct:.2f}% A-grade.",
        f"Security: {security['total_cves']} known CVEs across {security['agents_with_cves']} agents.",
        f"Maintenance: {maintenance['freshness_30d_pct']:.1f}% of agents updated in last 30 days.",
        f"License coverage: {license_idx['total_licensed']:,} agents with known licenses ({license_idx['index']:.0f}% permissive).",
    ]
    return "\n".join(lines)


def run_index_calculation():
    """Main entry point. Calculates all indices and stores in SQLite."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()

    pgconn = _pg_conn()
    sconn = sqlite3.connect(str(SQLITE_PATH))
    _ensure_table(sconn)

    try:
        # Calculate all components
        overall = calculate_overall_index(pgconn)
        grades = calculate_grade_distribution(pgconn)
        sources = calculate_source_indices(pgconn)
        categories = calculate_category_indices(pgconn)
        security = calculate_security_subindex(pgconn, sconn)
        maintenance = calculate_maintenance_subindex(pgconn)
        license_idx = calculate_license_subindex(sconn)
        framework_idx = calculate_framework_subindex(sconn)
        stars_corr = calculate_stars_trust_correlation(pgconn)

        summary = generate_summary(overall, grades, security, maintenance, license_idx)

        # Store indices
        indices = [
            ("overall", overall["weighted_index"], {
                "simple_avg": overall["simple_avg"],
                "median": overall["median"],
                "total_agents": overall["total_agents"],
                "stddev": overall["stddev"],
            }),
            ("security", security["index"], {
                "agents_scored": security["agents_scored"],
                "agents_with_cves": security["agents_with_cves"],
                "total_cves": security["total_cves"],
                "severity": security["severity_distribution"],
            }),
            ("maintenance", maintenance["index"], {
                "updated_30d": maintenance["updated_30d"],
                "freshness_pct": maintenance["freshness_30d_pct"],
            }),
            ("license", license_idx["index"], {
                "total_licensed": license_idx["total_licensed"],
                "permissive": license_idx["permissive"],
                "copyleft": license_idx["copyleft"],
            }),
        ]

        for name, value, meta in indices:
            prev_1d = _get_previous(sconn, name, 1)
            prev_7d = _get_previous(sconn, name, 7)
            prev_30d = _get_previous(sconn, name, 30)

            change_1d = round(value - prev_1d, 2) if prev_1d is not None else None
            change_7d = round(value - prev_7d, 2) if prev_7d is not None else None
            change_30d = round(value - prev_30d, 2) if prev_30d is not None else None

            sconn.execute("""
                INSERT OR REPLACE INTO ecosystem_index
                (date, index_name, value, change_1d, change_7d, change_30d, components, metadata, calculated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                today, name, value,
                change_1d, change_7d, change_30d,
                json.dumps(meta),
                json.dumps({"summary": summary}),
                now,
            ))

        # Store grade distribution as a separate entry
        sconn.execute("""
            INSERT OR REPLACE INTO ecosystem_index
            (date, index_name, value, components, metadata, calculated_at)
            VALUES (?, 'grade_distribution', ?, ?, ?, ?)
        """, (
            today,
            grades["total"],
            json.dumps(grades["counts"]),
            json.dumps(grades["percentages"]),
            now,
        ))

        # Store full snapshot for /index page
        snapshot = {
            "overall": overall,
            "grades": grades,
            "sources": sources,
            "categories": categories,
            "security": security,
            "maintenance": maintenance,
            "license": license_idx,
            "framework": framework_idx,
            "stars_correlation": stars_corr,
            "summary": summary,
        }
        sconn.execute("""
            INSERT OR REPLACE INTO ecosystem_index
            (date, index_name, value, components, metadata, calculated_at)
            VALUES (?, 'snapshot', ?, ?, ?, ?)
        """, (
            today,
            overall["weighted_index"],
            json.dumps(snapshot),
            json.dumps({"version": 1}),
            now,
        ))

        sconn.commit()

        print(f"\n{'='*60}")
        print(f"NERQ ECOSYSTEM TRUST INDEX — {today}")
        print(f"{'='*60}")
        print(summary)
        print(f"\nSub-indices:")
        print(f"  Security:    {security['index']}/100")
        print(f"  Maintenance: {maintenance['index']}/100")
        print(f"  License:     {license_idx['index']:.0f}% permissive")
        print(f"  Frameworks:  {framework_idx['agents_with_frameworks']} agents tracked")
        print(f"\nTop sources by trust:")
        for src, data in sorted(sources.items(), key=lambda x: x[1]["avg_score"], reverse=True)[:5]:
            print(f"  {src}: {data['avg_score']}/100 ({data['count']:,} agents)")
        print(f"\nStars → Trust correlation:")
        for bucket, data in stars_corr.items():
            print(f"  {bucket:>8s}: avg {data['avg']}, median {data['median']} ({data['count']:,} agents)")
        print(f"\nStored in: {SQLITE_PATH}")

        return snapshot

    finally:
        pgconn.close()
        sconn.close()


def get_latest_snapshot() -> dict | None:
    """Get the latest ecosystem index snapshot for the /index page."""
    try:
        sconn = sqlite3.connect(str(SQLITE_PATH))
        row = sconn.execute(
            "SELECT components, date FROM ecosystem_index WHERE index_name = 'snapshot' ORDER BY date DESC LIMIT 1"
        ).fetchone()
        sconn.close()
        if row:
            data = json.loads(row[0])
            data["date"] = row[1]
            return data
        return None
    except Exception as e:
        logger.warning(f"Failed to get ecosystem snapshot: {e}")
        return None


def get_index_history(index_name="overall", days=30) -> list:
    """Get historical index values for trend chart."""
    try:
        sconn = sqlite3.connect(str(SQLITE_PATH))
        rows = sconn.execute(
            "SELECT date, value FROM ecosystem_index WHERE index_name = ? ORDER BY date DESC LIMIT ?",
            (index_name, days)
        ).fetchall()
        sconn.close()
        return [{"date": r[0], "value": r[1]} for r in reversed(rows)]
    except Exception:
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_index_calculation()
