"""
Trend Detector — Daily 08:00
==============================
Detects rising/declining agents, framework momentum, security alerts.
Stores trends in agent_trends table for API and page consumption.

Usage:
    python -m agentindex.intelligence.trend_detector
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.sql import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [trend-detector] %(message)s")
logger = logging.getLogger("trend-detector")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            trend_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            magnitude REAL,
            details TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_at_name ON agent_trends(agent_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_at_type ON agent_trends(trend_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_at_date ON agent_trends(detected_at)")
    conn.commit()
    conn.close()


def _detect_trust_changes(conn):
    """Detect agents with significant trust score changes."""
    from agentindex.db.models import get_session
    session = get_session()
    now = datetime.now().isoformat()
    count = 0

    try:
        # Get agents with trust score snapshots (from dashboard data if exists)
        # For now, compare current scores against a recent baseline
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as current_score,
                   trust_grade, stars, category
            FROM agents
            WHERE is_active = true
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            ORDER BY stars DESC NULLS LAST
            LIMIT 5000
        """)).fetchall()

        for r in rows:
            d = dict(r._mapping)
            name = d["name"]
            score = float(d.get("current_score") or 0)
            stars = d.get("stars") or 0

            # Check for high-trust new entrants (trust >= 80 and stars > 500)
            if score >= 80 and stars > 500:
                existing = conn.execute(
                    "SELECT COUNT(*) FROM agent_trends WHERE agent_name = ? AND trend_type = 'high_trust' AND detected_at > datetime('now', '-7 days')",
                    (name,)
                ).fetchone()
                if existing[0] == 0:
                    conn.execute(
                        "INSERT INTO agent_trends (agent_name, trend_type, direction, magnitude, details, detected_at) "
                        "VALUES (?, 'high_trust', 'rising', ?, ?, ?)",
                        (name, score, json.dumps({"trust_score": score, "stars": stars, "grade": d.get("trust_grade")}), now)
                    )
                    count += 1

            # Detect popular agents (>5000 stars)
            if stars > 5000:
                existing = conn.execute(
                    "SELECT COUNT(*) FROM agent_trends WHERE agent_name = ? AND trend_type = 'popularity_surge' AND detected_at > datetime('now', '-7 days')",
                    (name,)
                ).fetchone()
                if existing[0] == 0:
                    conn.execute(
                        "INSERT INTO agent_trends (agent_name, trend_type, direction, magnitude, details, detected_at) "
                        "VALUES (?, 'popularity_surge', 'rising', ?, ?, ?)",
                        (name, stars, json.dumps({"stars": stars, "trust_score": score}), now)
                    )
                    count += 1

        conn.commit()
    finally:
        session.close()

    return count


def _detect_security_alerts(conn):
    """Detect new critical/high CVEs affecting popular agents."""
    now = datetime.now().isoformat()
    count = 0

    try:
        cves = conn.execute("""
            SELECT agent_name, cve_id, severity, description
            FROM agent_vulnerabilities
            WHERE severity IN ('CRITICAL', 'HIGH')
            AND cve_id NOT IN (
                SELECT agent_name FROM agent_trends
                WHERE trend_type = 'security_alert' AND detected_at > datetime('now', '-30 days')
            )
            LIMIT 20
        """).fetchall()

        for r in cves:
            agent = r[0]
            cve_id = r[1]
            severity = r[2]

            existing = conn.execute(
                "SELECT COUNT(*) FROM agent_trends WHERE agent_name = ? AND trend_type = 'security_alert' AND details LIKE ?",
                (agent, f"%{cve_id}%")
            ).fetchone()
            if existing[0] == 0:
                conn.execute(
                    "INSERT INTO agent_trends (agent_name, trend_type, direction, magnitude, details, detected_at) "
                    "VALUES (?, 'security_alert', 'alert', ?, ?, ?)",
                    (agent, 1.0 if severity == "CRITICAL" else 0.7,
                     json.dumps({"cve_id": cve_id, "severity": severity, "description": (r[3] or "")[:200]}), now)
                )
                count += 1

        conn.commit()
    except Exception as e:
        logger.warning(f"Security alert detection error: {e}")

    return count


def _detect_framework_momentum(conn):
    """Detect frameworks gaining or losing agents."""
    now = datetime.now().isoformat()
    count = 0

    try:
        fw_counts = conn.execute("""
            SELECT framework, COUNT(DISTINCT agent_name) as cnt
            FROM agent_frameworks
            GROUP BY framework
            ORDER BY cnt DESC
        """).fetchall()

        for fw, agent_count in fw_counts:
            if agent_count >= 5:
                existing = conn.execute(
                    "SELECT COUNT(*) FROM agent_trends WHERE agent_name = ? AND trend_type = 'framework_shift' AND detected_at > datetime('now', '-7 days')",
                    (fw,)
                ).fetchone()
                if existing[0] == 0:
                    conn.execute(
                        "INSERT INTO agent_trends (agent_name, trend_type, direction, magnitude, details, detected_at) "
                        "VALUES (?, 'framework_shift', 'rising', ?, ?, ?)",
                        (fw, agent_count, json.dumps({"agent_count": agent_count}), now)
                    )
                    count += 1

        conn.commit()
    except Exception as e:
        logger.warning(f"Framework momentum error: {e}")

    return count


def _detect_new_entrants(conn):
    """Detect notable new agents (high stars, rapid adoption)."""
    from agentindex.db.models import get_session
    session = get_session()
    now = datetime.now().isoformat()
    count = 0

    try:
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as ts, stars, category
            FROM agents
            WHERE is_active = true
              AND first_indexed > NOW() - INTERVAL '7 days'
              AND stars > 100
            ORDER BY stars DESC
            LIMIT 20
        """)).fetchall()

        for r in rows:
            d = dict(r._mapping)
            conn.execute(
                "INSERT INTO agent_trends (agent_name, trend_type, direction, magnitude, details, detected_at) "
                "VALUES (?, 'new_entrant', 'new', ?, ?, ?)",
                (d["name"], float(d.get("ts") or 0),
                 json.dumps({"trust_score": float(d.get("ts") or 0), "stars": d.get("stars"), "category": d.get("category")}), now)
            )
            count += 1

        conn.commit()
    finally:
        session.close()

    return count


def _post_critical_alerts(conn):
    """Auto-publish critical security alerts to Bluesky."""
    try:
        from agentindex.bluesky_bot import post_to_bluesky
        alerts = conn.execute("""
            SELECT agent_name, details FROM agent_trends
            WHERE trend_type = 'security_alert'
            AND direction = 'alert'
            AND magnitude >= 1.0
            AND detected_at > datetime('now', '-1 day')
            LIMIT 3
        """).fetchall()

        for r in alerts:
            details = json.loads(r[1]) if r[1] else {}
            text = (
                f"Security Alert: {r[0]} has a {details.get('severity', 'CRITICAL')} vulnerability "
                f"({details.get('cve_id', 'Unknown')}). Trust score updated.\n\n"
                f"Check: nerq.ai/safe/{r[0].lower().replace('/', '').replace(' ', '-')}"
            )
            post_to_bluesky(text)
            logger.info(f"  Bluesky alert posted for {r[0]}")
    except Exception as e:
        logger.warning(f"  Bluesky alert posting skipped: {e}")


def detect_all():
    """Run all trend detection and return summary."""
    _init_db()
    conn = sqlite3.connect(str(SQLITE_DB))

    trust_changes = _detect_trust_changes(conn)
    logger.info(f"  Trust/popularity trends: {trust_changes}")

    security_alerts = _detect_security_alerts(conn)
    logger.info(f"  Security alerts: {security_alerts}")

    framework_trends = _detect_framework_momentum(conn)
    logger.info(f"  Framework momentum: {framework_trends}")

    new_entrants = _detect_new_entrants(conn)
    logger.info(f"  New entrants: {new_entrants}")

    # Summary
    total_7d = conn.execute(
        "SELECT COUNT(*) FROM agent_trends WHERE detected_at > datetime('now', '-7 days')"
    ).fetchone()[0]

    rising = conn.execute(
        "SELECT COUNT(*) FROM agent_trends WHERE direction = 'rising' AND detected_at > datetime('now', '-7 days')"
    ).fetchone()[0]

    alerts = conn.execute(
        "SELECT COUNT(*) FROM agent_trends WHERE direction = 'alert' AND detected_at > datetime('now', '-7 days')"
    ).fetchone()[0]

    # Post critical alerts to Bluesky
    if security_alerts > 0:
        _post_critical_alerts(conn)

    conn.close()

    return {
        "total_trends_7d": total_7d,
        "trust_changes": trust_changes,
        "security_alerts": security_alerts,
        "framework_trends": framework_trends,
        "new_entrants": new_entrants,
        "rising": rising,
        "alerts": alerts,
    }


def main():
    logger.info("=" * 60)
    logger.info("Trend Detector — starting")
    logger.info("=" * 60)

    result = detect_all()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Trend Detector — COMPLETE")
    logger.info(f"  Total trends (7d): {result['total_trends_7d']}")
    logger.info(f"  Rising: {result['rising']}")
    logger.info(f"  Alerts: {result['alerts']}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
