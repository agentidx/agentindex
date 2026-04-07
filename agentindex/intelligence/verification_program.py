"""
Verification Program — Daily 09:30
====================================
Checks agents for "Verified by Nerq" status based on sustained trust scores.
VERIFIED: trust score >= 80 for 30+ days
VERIFIED_PLUS: trust score >= 90 for 30+ days

Usage:
    python -m agentindex.intelligence.verification_program
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.sql import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [verification] %(message)s")
logger = logging.getLogger("verification")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
THRESHOLD_VERIFIED = 80
THRESHOLD_VERIFIED_PLUS = 90
MIN_DAYS = 30
GRACE_DAYS = 7


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB), timeout=30)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS verified_agents (
            agent_name TEXT PRIMARY KEY,
            verification_level TEXT NOT NULL,
            verified_since TIMESTAMP,
            current_score REAL,
            consecutive_days_above_threshold INTEGER DEFAULT 0,
            badge_url TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_va_level ON verified_agents(verification_level)")
    conn.commit()
    conn.close()


def _check_trust_history(conn, agent_name, threshold):
    """Check if agent has maintained trust score above threshold for MIN_DAYS."""
    try:
        row = conn.execute(
            "SELECT trust_score_history FROM agent_dashboard WHERE agent_name = ?",
            (agent_name,)
        ).fetchone()
        if not row or not row[0]:
            return 0

        history = json.loads(row[0])
        if not history:
            return 0

        # Count consecutive days above threshold from most recent
        consecutive = 0
        for entry in reversed(history):
            score = entry.get("score", 0)
            if score >= threshold:
                consecutive += 1
            else:
                break

        return consecutive
    except Exception:
        return 0


def run_verification():
    """Run the verification program."""
    _init_db()

    from agentindex.db.models import get_session
    session = get_session()
    conn = sqlite3.connect(str(SQLITE_DB), timeout=30)
    now = datetime.now().isoformat()

    try:
        # Get all agents with trust score >= 80
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as ts
            FROM entity_lookup
            WHERE is_active = true
              AND COALESCE(trust_score_v2, trust_score) >= :threshold
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
        """), {"threshold": THRESHOLD_VERIFIED}).fetchall()

        logger.info(f"Found {len(rows)} agents with trust score >= {THRESHOLD_VERIFIED}")

        newly_verified = 0
        newly_plus = 0
        removed = 0
        total_verified = 0
        total_plus = 0

        for r in rows:
            d = dict(r._mapping)
            agent_name = d["name"]
            score = float(d["ts"])

            # Check history for VERIFIED_PLUS threshold
            if score >= THRESHOLD_VERIFIED_PLUS:
                days = _check_trust_history(conn, agent_name, THRESHOLD_VERIFIED_PLUS)
                if days >= MIN_DAYS:
                    level = "VERIFIED_PLUS"
                else:
                    # Fall back to checking VERIFIED threshold
                    days = _check_trust_history(conn, agent_name, THRESHOLD_VERIFIED)
                    level = "VERIFIED" if days >= MIN_DAYS else None
            else:
                days = _check_trust_history(conn, agent_name, THRESHOLD_VERIFIED)
                level = "VERIFIED" if days >= MIN_DAYS else None

            if level:
                # Check if already verified
                existing = conn.execute(
                    "SELECT verification_level FROM verified_agents WHERE agent_name = ?",
                    (agent_name,)
                ).fetchone()

                slug = agent_name.lower().replace("/", "").replace(" ", "-")
                badge_url = f"https://nerq.ai/badge/{slug}/verified.svg"
                if level == "VERIFIED_PLUS":
                    badge_url = f"https://nerq.ai/badge/{slug}/verified-plus.svg"

                conn.execute("""
                    INSERT OR REPLACE INTO verified_agents
                    (agent_name, verification_level, verified_since, current_score, consecutive_days_above_threshold, badge_url)
                    VALUES (?, ?, COALESCE((SELECT verified_since FROM verified_agents WHERE agent_name = ?), ?), ?, ?, ?)
                """, (agent_name, level, agent_name, now, score, days, badge_url))

                if not existing:
                    if level == "VERIFIED_PLUS":
                        newly_plus += 1
                    else:
                        newly_verified += 1
                elif existing[0] != level and level == "VERIFIED_PLUS":
                    newly_plus += 1

                if level == "VERIFIED_PLUS":
                    total_plus += 1
                else:
                    total_verified += 1

        # Handle agents that dropped below threshold (with grace period)
        all_verified = conn.execute("SELECT agent_name FROM verified_agents").fetchall()
        verified_names = [r[0] for r in all_verified]

        if verified_names:
            for vname in verified_names:
                current = session.execute(text("""
                    SELECT COALESCE(trust_score_v2, trust_score) as ts
                    FROM agents WHERE name = :n AND is_active = true
                """), {"n": vname}).fetchone()
                if current:
                    cs = float(current[0]) if current[0] else 0
                    if cs < THRESHOLD_VERIFIED:
                        # Check grace period
                        days_below = _check_trust_history(conn, vname, THRESHOLD_VERIFIED)
                        if days_below == 0:  # Currently below
                            conn.execute("DELETE FROM verified_agents WHERE agent_name = ?", (vname,))
                            removed += 1

        conn.commit()

    finally:
        session.close()
        conn.close()

    return {
        "newly_verified": newly_verified,
        "newly_plus": newly_plus,
        "removed": removed,
        "total_verified": total_verified,
        "total_plus": total_plus,
        "total": total_verified + total_plus,
    }


def main():
    logger.info("=" * 60)
    logger.info("Verification Program — starting")
    logger.info("=" * 60)

    result = run_verification()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Verification Program — COMPLETE")
    logger.info(f"  Newly VERIFIED: {result['newly_verified']}")
    logger.info(f"  Newly VERIFIED_PLUS: {result['newly_plus']}")
    logger.info(f"  Removed: {result['removed']}")
    logger.info(f"  Total VERIFIED: {result['total_verified']}")
    logger.info(f"  Total VERIFIED_PLUS: {result['total_plus']}")
    logger.info(f"  Total verified agents: {result['total']}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
