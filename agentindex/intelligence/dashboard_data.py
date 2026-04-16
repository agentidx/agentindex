"""
Dashboard Data Aggregator — Daily 09:00
=========================================
Computes and caches dashboard metrics for each agent.

Usage:
    python -m agentindex.intelligence.dashboard_data
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.sql import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [dashboard-data] %(message)s")
logger = logging.getLogger("dashboard-data")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_dashboard (
            agent_name TEXT PRIMARY KEY,
            trust_score_history TEXT,
            preflight_checks_7d INTEGER DEFAULT 0,
            preflight_checks_30d INTEGER DEFAULT 0,
            page_views_7d INTEGER DEFAULT 0,
            badge_displays_7d INTEGER DEFAULT 0,
            category_rank INTEGER,
            category_total INTEGER,
            category_avg_trust REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ad_rank ON agent_dashboard(category_rank)")
    conn.commit()
    conn.close()


def _compute_category_stats(session):
    """Compute category rankings and averages."""
    session.execute(text("SET LOCAL statement_timeout = '60s'"))
    rows = session.execute(text("""
        SELECT name, category, COALESCE(trust_score_v2, trust_score) as ts
        FROM entity_lookup
        WHERE is_active = true
          AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
        ORDER BY category, COALESCE(trust_score_v2, trust_score) DESC
    """)).fetchall()

    # Group by category
    categories = {}
    for r in rows:
        d = dict(r._mapping)
        cat = d.get("category") or "uncategorized"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({"name": d["name"], "trust_score": float(d["ts"] or 0)})

    # Compute rank, total, avg
    result = {}
    for cat, agents in categories.items():
        total = len(agents)
        avg = sum(a["trust_score"] for a in agents) / max(total, 1)
        for rank, agent in enumerate(agents, 1):
            result[agent["name"]] = {
                "category": cat,
                "rank": rank,
                "total": total,
                "avg_trust": round(avg, 1),
            }

    return result


def _build_trust_history(agent_name, current_score, conn):
    """Build trust score history. For now, record current snapshot."""
    try:
        existing = conn.execute(
            "SELECT trust_score_history FROM agent_dashboard WHERE agent_name = ?",
            (agent_name,)
        ).fetchone()

        history = []
        if existing and existing[0]:
            try:
                history = json.loads(existing[0])
            except (json.JSONDecodeError, TypeError):
                history = []

        today = datetime.now().strftime("%Y-%m-%d")

        # Don't duplicate today's entry
        if history and history[-1].get("date") == today:
            history[-1]["score"] = current_score
        else:
            history.append({"date": today, "score": current_score})

        # Keep last 90 days
        history = history[-90:]
        return json.dumps(history)
    except Exception:
        return json.dumps([{"date": datetime.now().strftime("%Y-%m-%d"), "score": current_score}])


def compute_dashboards(limit=10000):
    """Compute dashboard data for top agents."""
    _init_db()

    from agentindex.db.models import get_session
    session = get_session()
    conn = sqlite3.connect(str(SQLITE_DB))
    now = datetime.now().isoformat()

    try:
        # Get category stats
        logger.info("  Computing category rankings...")
        cat_stats = _compute_category_stats(session)
        logger.info(f"  Category stats computed for {len(cat_stats)} agents")

        # Get top agents
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as ts, category
            FROM entity_lookup
            WHERE is_active = true
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()

        processed = 0
        for r in rows:
            d = dict(r._mapping)
            name = d["name"]
            score = float(d.get("ts") or 0)

            cs = cat_stats.get(name, {"rank": None, "total": None, "avg_trust": None})
            history = _build_trust_history(name, score, conn)

            from agentindex.crypto.dual_write import dual_execute
            dual_execute(conn, """
                INSERT OR REPLACE INTO agent_dashboard
                (agent_name, trust_score_history, category_rank, category_total, category_avg_trust, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, history, cs.get("rank"), cs.get("total"), cs.get("avg_trust"), now))

            processed += 1
            if processed % 1000 == 0:
                conn.commit()
                logger.info(f"  Progress: {processed}/{len(rows)}")

        conn.commit()
        logger.info(f"  Dashboard data computed for {processed} agents")

        # Summary stats
        top_ranked = conn.execute("""
            SELECT agent_name, category_rank, category_total, category_avg_trust
            FROM agent_dashboard
            WHERE category_rank = 1
            ORDER BY category_avg_trust DESC
            LIMIT 10
        """).fetchall()

    finally:
        conn.close()
        session.close()

    return {
        "processed": processed,
        "top_ranked": [(r[0], r[1], r[2]) for r in (top_ranked or [])],
    }


def main():
    logger.info("=" * 60)
    logger.info("Dashboard Data Aggregator — starting")
    logger.info("=" * 60)

    result = compute_dashboards()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Dashboard Data Aggregator — COMPLETE")
    logger.info(f"  Agents processed: {result['processed']}")
    if result.get("top_ranked"):
        logger.info(f"  #1 ranked in their categories:")
        for name, rank, total in result["top_ranked"][:5]:
            logger.info(f"    {name}: #1 of {total}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
