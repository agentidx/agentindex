#!/usr/bin/env python3
"""
Nerq Predictive Intelligence — Layer 1: Observations
=====================================================
Collects daily snapshots of top 10,000 agents.
Run daily at 05:00 via LaunchAgent com.nerq.pred-observations.

Usage:
    python3 agentindex/intelligence/predictive/observations.py
"""

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agentindex.db.models import get_db_session
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-6s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/pred-observations.log"),
    ],
)
logger = logging.getLogger("nerq.pred.observations")

ANALYTICS_DB = str(Path(__file__).parent.parent.parent.parent / "logs" / "analytics.db")
TODAY = date.today()
BATCH_SIZE = 500
TOP_N = 10000


def get_ai_crawl_counts() -> dict:
    """Query analytics DB for AI crawl counts per agent path in last 24h."""
    counts = {}
    if not os.path.exists(ANALYTICS_DB):
        logger.warning(f"Analytics DB not found: {ANALYTICS_DB}")
        return counts

    try:
        conn = sqlite3.connect(ANALYTICS_DB, timeout=5)

        since = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        # Crawl counts by path
        rows = conn.execute("""
            SELECT path,
                   SUM(CASE WHEN user_agent LIKE '%ChatGPT-User%' THEN 1 ELSE 0 END) as chatgpt,
                   SUM(CASE WHEN user_agent LIKE '%Perplexity%' THEN 1 ELSE 0 END) as perplexity,
                   SUM(CASE WHEN user_agent LIKE '%ClaudeBot%' OR user_agent LIKE '%Claude-User%' THEN 1 ELSE 0 END) as claude,
                   SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) as human,
                   COUNT(*) as total
            FROM requests
            WHERE ts > ?
            AND (path LIKE '/safe/%' OR path LIKE '/agent/%' OR path LIKE '/is-%'
                 OR path LIKE '/model/%' OR path LIKE '/package/%')
            GROUP BY path
        """, (since,)).fetchall()

        for row in rows:
            path = row[0]
            slug = path.split("/")[-1] if "/" in path else path
            slug = slug.lower().replace("-safe", "").strip("-")
            if slug:
                if slug not in counts:
                    counts[slug] = {"chatgpt": 0, "perplexity": 0, "claude": 0, "human": 0, "total": 0}
                counts[slug]["chatgpt"] += row[1]
                counts[slug]["perplexity"] += row[2]
                counts[slug]["claude"] += row[3]
                counts[slug]["human"] += row[4]
                counts[slug]["total"] += row[5]

        # Preflight checks from dedicated table
        pf_rows = conn.execute("""
            SELECT LOWER(target) as target, COUNT(*) as cnt
            FROM preflight_analytics
            WHERE ts > ?
            GROUP BY LOWER(target)
        """, (since,)).fetchall()

        for row in pf_rows:
            target = (row[0] or "").strip()
            if target:
                if target not in counts:
                    counts[target] = {"chatgpt": 0, "perplexity": 0, "claude": 0, "human": 0, "total": 0}
                counts[target]["preflight"] = row[1]

        conn.close()
    except Exception as e:
        logger.warning(f"Analytics query failed: {e}")

    return counts


def collect_observations():
    """Collect daily observations for top 10,000 agents."""
    start = time.time()
    logger.info(f"Starting observation collection for {TODAY}")

    with get_db_session() as session:
        # Get top agents by stars
        rows = session.execute(text("""
            SELECT id, name, stars, forks, downloads, trust_score, trust_score_v2,
                   category, agent_type, source,
                   security_score, activity_score, documentation_score, popularity_score
            FROM agents
            WHERE is_active = true
            ORDER BY COALESCE(stars, 0) DESC
            LIMIT :limit
        """), {"limit": TOP_N}).fetchall()

        logger.info(f"Fetched {len(rows)} agents from database")

        # Get AI crawl counts from analytics
        ai_counts = get_ai_crawl_counts()
        logger.info(f"Got AI crawl data for {len(ai_counts)} paths")

        # Insert observations in batches
        inserted = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            values = []

            for r in batch:
                agent_id = r[0]
                name = r[1]
                slug = name.lower().split("/")[-1] if name else ""

                # Look up AI counts by various slug patterns
                ac = ai_counts.get(slug, {})
                if not ac and "/" in (name or ""):
                    ac = ai_counts.get(name.lower().replace("/", "-"), {})

                values.append({
                    "agent_id": agent_id,
                    "agent_name": name,
                    "observed_at": TODAY.isoformat(),
                    "stars": r[2],
                    "forks": r[3],
                    "downloads": r[4],
                    "trust_score": r[5],
                    "trust_score_v2": r[6],
                    "ai_crawls_24h": ac.get("total", 0),
                    "chatgpt_crawls": ac.get("chatgpt", 0),
                    "perplexity_crawls": ac.get("perplexity", 0),
                    "claude_crawls": ac.get("claude", 0),
                    "human_visits": ac.get("human", 0),
                    "preflight_checks": ac.get("preflight", 0),
                    "raw_data": json.dumps({
                        "category": r[7],
                        "agent_type": r[8],
                        "source": r[9],
                        "security_score": float(r[10]) if r[10] else None,
                        "activity_score": float(r[11]) if r[11] else None,
                        "documentation_score": float(r[12]) if r[12] else None,
                        "popularity_score": float(r[13]) if r[13] else None,
                    }),
                })

            try:
                session.execute(text("""
                    INSERT INTO prediction_observations
                        (agent_id, agent_name, observed_at, stars, forks, downloads,
                         trust_score, trust_score_v2, ai_crawls_24h,
                         chatgpt_crawls, perplexity_crawls, claude_crawls,
                         human_visits, preflight_checks, raw_data)
                    VALUES
                        (:agent_id, :agent_name, :observed_at, :stars, :forks, :downloads,
                         :trust_score, :trust_score_v2, :ai_crawls_24h,
                         :chatgpt_crawls, :perplexity_crawls, :claude_crawls,
                         :human_visits, :preflight_checks, CAST(:raw_data AS jsonb))
                    ON CONFLICT (agent_id, observed_at) DO NOTHING
                """), values)
                session.flush()
                inserted += len(batch)
                logger.info(f"  Batch {i // BATCH_SIZE + 1}: inserted up to {inserted} rows")
            except Exception as e:
                logger.error(f"Batch insert failed: {e}")
                session.rollback()

        elapsed = time.time() - start
        logger.info(f"Observation collection complete: {inserted} agents, {elapsed:.1f}s")
        return inserted


if __name__ == "__main__":
    count = collect_observations()
    print(f"Collected {count} observations for {TODAY}")
