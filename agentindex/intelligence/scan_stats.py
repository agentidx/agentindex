"""
Scan Statistics — aggregates project_scans data into a stats JSON file.

Usage:
    python -m agentindex.intelligence.scan_stats

Also provides mount_scan_stats(app) for the GET /v1/scan-stats endpoint.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.sql import text

from agentindex.db.models import get_engine

logger = logging.getLogger("agentindex.intelligence.scan_stats")

STATS_OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "scan_stats.json",
)


def compute_scan_stats() -> dict:
    """Query project_scans and compute aggregate statistics."""
    engine = get_engine()
    stats = {}

    with engine.connect() as conn:
        # Total scanned
        row = conn.execute(text("SELECT COUNT(*) FROM project_scans")).fetchone()
        stats["total_scanned"] = row[0] if row else 0

        # Percentage with critical CVEs
        if stats["total_scanned"] > 0:
            row = conn.execute(text(
                "SELECT COUNT(*) FROM project_scans WHERE critical_cves > 0"
            )).fetchone()
            crit_count = row[0] if row else 0
            stats["pct_with_critical"] = round(
                (crit_count / stats["total_scanned"]) * 100, 1
            )
        else:
            stats["pct_with_critical"] = 0.0

        # Percentage without license
        if stats["total_scanned"] > 0:
            row = conn.execute(text(
                "SELECT COUNT(*) FROM project_scans WHERE deps_without_license > 0"
            )).fetchone()
            no_lic_count = row[0] if row else 0
            stats["pct_no_license"] = round(
                (no_lic_count / stats["total_scanned"]) * 100, 1
            )
        else:
            stats["pct_no_license"] = 0.0

        # Grade distribution
        grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        rows = conn.execute(text(
            "SELECT project_health_grade, COUNT(*) FROM project_scans "
            "WHERE project_health_grade IN ('A', 'B', 'C', 'D', 'F') "
            "GROUP BY project_health_grade"
        )).fetchall()
        for row in rows:
            grade_dist[row[0]] = row[1]
        stats["grade_distribution"] = grade_dist

        # Top 20 healthiest: A-grade repos by stars
        rows = conn.execute(text(
            "SELECT repo_full_name, avg_trust_score, github_stars FROM project_scans "
            "WHERE project_health_grade = 'A' "
            "ORDER BY github_stars DESC NULLS LAST LIMIT 20"
        )).fetchall()
        stats["top_healthiest"] = [
            {"repo_full_name": r[0], "avg_trust_score": round(r[1], 1) if r[1] else None, "github_stars": r[2]}
            for r in rows
        ]

        # Top 20 at-risk: D/F-grade repos by stars
        rows = conn.execute(text(
            "SELECT repo_full_name, avg_trust_score, project_health_grade, github_stars FROM project_scans "
            "WHERE project_health_grade IN ('D', 'F') "
            "ORDER BY github_stars DESC NULLS LAST LIMIT 20"
        )).fetchall()
        stats["top_at_risk"] = [
            {
                "repo_full_name": r[0],
                "avg_trust_score": round(r[1], 1) if r[1] else None,
                "grade": r[2],
                "github_stars": r[3],
            }
            for r in rows
        ]

        # Average trust score overall
        row = conn.execute(text(
            "SELECT AVG(avg_trust_score) FROM project_scans "
            "WHERE avg_trust_score IS NOT NULL"
        )).fetchone()
        stats["avg_trust_overall"] = round(row[0], 1) if row and row[0] else 0.0

        # Scanned this week
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        row = conn.execute(
            text("SELECT COUNT(*) FROM project_scans WHERE scanned_at > :cutoff"),
            {"cutoff": seven_days_ago},
        ).fetchone()
        stats["scanned_this_week"] = row[0] if row else 0

    stats["generated_at"] = datetime.utcnow().isoformat() + "Z"
    return stats


def save_stats():
    """Compute stats and save to the data directory."""
    stats = compute_scan_stats()

    # Ensure output directory exists
    os.makedirs(os.path.dirname(STATS_OUTPUT_PATH), exist_ok=True)

    with open(STATS_OUTPUT_PATH, "w") as f:
        json.dump(stats, f, indent=2)

    logger.info(f"Scan stats saved to {STATS_OUTPUT_PATH}")
    return stats


def mount_scan_stats(app):
    """Mount the GET /v1/scan-stats endpoint on the FastAPI app."""

    @app.get("/v1/scan-stats")
    async def scan_stats():
        """Return aggregate scan statistics."""
        # Try to read from the cached file first
        if os.path.exists(STATS_OUTPUT_PATH):
            try:
                with open(STATS_OUTPUT_PATH, "r") as f:
                    cached = json.load(f)
                # If generated less than 1 hour ago, return cached
                generated_at = cached.get("generated_at", "")
                if generated_at:
                    gen_time = datetime.fromisoformat(generated_at.rstrip("Z"))
                    if datetime.utcnow() - gen_time < timedelta(hours=1):
                        return cached
            except (json.JSONDecodeError, ValueError, OSError):
                pass

        # Recompute
        stats = compute_scan_stats()

        # Save for next time
        try:
            os.makedirs(os.path.dirname(STATS_OUTPUT_PATH), exist_ok=True)
            with open(STATS_OUTPUT_PATH, "w") as f:
                json.dump(stats, f, indent=2)
        except OSError as e:
            logger.warning(f"Could not save scan stats: {e}")

        return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stats = save_stats()
    print(json.dumps(stats, indent=2))
