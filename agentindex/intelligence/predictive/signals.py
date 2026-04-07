#!/usr/bin/env python3
"""
Nerq Predictive Intelligence — Layer 2: Derived Signals
========================================================
Calculates velocity, acceleration, momentum, AI attention, and health signals.
Requires ≥2 days of observations (7 days ideal).
Run daily at 05:30 via LaunchAgent com.nerq.pred-signals.
"""

import json
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agentindex.db.models import get_db_session
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-6s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/pred-signals.log")],
)
logger = logging.getLogger("nerq.pred.signals")

TODAY = date.today()


def calculate_signals():
    """Calculate derived signals from observations."""
    start = time.time()
    logger.info(f"Calculating signals for {TODAY}")

    from agentindex.db.models import get_session
    session = get_session()
    try:
        # Get agents with at least 2 days of observations
        agents = session.execute(text("""
            SELECT DISTINCT agent_id, agent_name
            FROM prediction_observations
            WHERE observed_at >= :cutoff
            GROUP BY agent_id, agent_name
            HAVING COUNT(DISTINCT observed_at) >= 2
        """), {"cutoff": (TODAY - timedelta(days=14)).isoformat()}).fetchall()

        logger.info(f"Found {len(agents)} agents with sufficient observations")

        # Get category averages for momentum calculation
        cat_avgs = {}
        if agents:
            cat_rows = session.execute(text("""
                SELECT o1.raw_data->>'category' as cat,
                       AVG(o2.stars - o1.stars) as avg_star_vel
                FROM prediction_observations o1
                JOIN prediction_observations o2 ON o1.agent_id = o2.agent_id
                    AND o2.observed_at = (SELECT MAX(observed_at) FROM prediction_observations WHERE agent_id = o1.agent_id)
                    AND o1.observed_at = (SELECT MIN(observed_at) FROM prediction_observations WHERE agent_id = o1.agent_id AND observed_at >= :cutoff)
                WHERE o1.observed_at >= :cutoff
                GROUP BY cat
            """), {"cutoff": (TODAY - timedelta(days=7)).isoformat()}).fetchall()
            for r in cat_rows:
                if r[0]:
                    cat_avgs[r[0]] = r[1] or 1

        inserted = 0
        for agent_id, agent_name in agents:
            try:
                # Get latest and earliest observations
                obs = session.execute(text("""
                    SELECT observed_at, stars, downloads, trust_score_v2,
                           ai_crawls_24h, chatgpt_crawls, perplexity_crawls, claude_crawls,
                           human_visits, preflight_checks, raw_data
                    FROM prediction_observations
                    WHERE agent_id = :aid AND observed_at >= :cutoff
                    ORDER BY observed_at ASC
                """), {"aid": str(agent_id), "cutoff": (TODAY - timedelta(days=14)).isoformat()}).fetchall()

                if len(obs) < 2:
                    continue

                latest = obs[-1]
                earliest = obs[0]
                days_span = max(1, (date.fromisoformat(str(latest[0])) - date.fromisoformat(str(earliest[0]))).days)

                # Velocity (total change / days)
                star_vel = ((latest[1] or 0) - (earliest[1] or 0))
                dl_vel = ((latest[2] or 0) - (earliest[2] or 0))

                # Acceleration (compare first half vs second half velocity)
                mid = len(obs) // 2
                if mid > 0 and len(obs) > 2:
                    first_half_vel = ((obs[mid][1] or 0) - (obs[0][1] or 0))
                    second_half_vel = ((obs[-1][1] or 0) - (obs[mid][1] or 0))
                    star_accel = second_half_vel - first_half_vel
                    first_half_dl = ((obs[mid][2] or 0) - (obs[0][2] or 0))
                    second_half_dl = ((obs[-1][2] or 0) - (obs[mid][2] or 0))
                    dl_accel = second_half_dl - first_half_dl
                else:
                    star_accel = 0
                    dl_accel = 0

                # AI attention
                ai_score = (latest[5] or 0) * 3 + (latest[6] or 0) * 2 + (latest[7] or 0) * 1
                ai_earliest = (earliest[5] or 0) * 3 + (earliest[6] or 0) * 2 + (earliest[7] or 0) * 1
                ai_delta = ai_score - ai_earliest

                # Commit freshness from raw_data
                _rd = latest[10]
                raw = json.loads(_rd) if isinstance(_rd, str) else (_rd if _rd else {})
                activity = raw.get("activity_score") or 50
                commit_fresh = max(0, 100 - int(activity)) if activity else 999

                # Issue resolution rate (approximated from activity score)
                issue_rate = (activity or 50) / 100.0

                # Bus factor (approximated: high popularity + low activity = fragile)
                pop = raw.get("popularity_score") or 50
                bus = min(5, max(1, int(pop / 25)))

                # Ecosystem breadth
                source = raw.get("source", "")
                breadth = sum(1 for s in ["github", "npm", "pypi", "huggingface", "docker"]
                             if s in (source or "").lower())
                breadth = max(1, breadth)

                # Fork/star ratio
                fork_ratio = 0.0  # We don't have forks in observations yet

                # Momentum vs category
                cat = raw.get("category", "")
                cat_avg = cat_avgs.get(cat, 1)
                momentum = star_vel / max(1, abs(cat_avg)) if cat_avg else 1.0

                signals = {
                    "star_velocity_7d": star_vel,
                    "star_acceleration": star_accel,
                    "download_velocity_7d": dl_vel,
                    "download_acceleration": dl_accel,
                    "ai_attention_score": ai_score,
                    "ai_attention_delta_7d": ai_delta,
                    "commit_freshness_days": commit_fresh,
                    "issue_resolution_rate": round(issue_rate, 3),
                    "bus_factor": bus,
                    "ecosystem_breadth": breadth,
                    "fork_star_ratio": round(fork_ratio, 3),
                    "momentum_vs_category": round(momentum, 3),
                    "trust_score": latest[3],
                    "stars": latest[1],
                    "downloads": latest[2],
                    "human_visits": latest[8],
                    "preflight_checks": latest[9],
                }

                session.execute(text("""
                    INSERT INTO prediction_signals
                        (agent_id, agent_name, calculated_at, star_velocity_7d, star_acceleration,
                         download_velocity_7d, download_acceleration, ai_attention_score,
                         ai_attention_delta_7d, commit_freshness_days, issue_resolution_rate,
                         bus_factor, ecosystem_breadth, fork_star_ratio, momentum_vs_category,
                         signals_json)
                    VALUES
                        (:aid, :name, :today, :sv, :sa, :dv, :da, :ai, :aid7,
                         :cf, :irr, :bf, :eb, :fsr, :mvc, CAST(:sj AS jsonb))
                    ON CONFLICT (agent_id, calculated_at) DO UPDATE SET
                        star_velocity_7d = EXCLUDED.star_velocity_7d,
                        signals_json = EXCLUDED.signals_json
                """), {
                    "aid": str(agent_id), "name": agent_name, "today": TODAY.isoformat(),
                    "sv": star_vel, "sa": star_accel, "dv": dl_vel, "da": dl_accel,
                    "ai": ai_score, "aid7": ai_delta, "cf": commit_fresh,
                    "irr": round(issue_rate, 3), "bf": bus, "eb": breadth,
                    "fsr": round(fork_ratio, 3), "mvc": round(momentum, 3),
                    "sj": json.dumps(signals),
                })
                inserted += 1

                if inserted % 500 == 0:
                    session.commit()
                    logger.info(f"  Processed {inserted} agents...")

            except Exception as e:
                logger.warning(f"Signal calc failed for {agent_name}: {e}")
                session.rollback()

        session.commit()
        elapsed = time.time() - start
        logger.info(f"Signal calculation complete: {inserted} agents, {elapsed:.1f}s")
        return inserted

    finally:
        session.close()


if __name__ == "__main__":
    count = calculate_signals()
    print(f"Calculated signals for {count} agents on {TODAY}")
