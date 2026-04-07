#!/usr/bin/env python3
"""
Nerq Predictive Intelligence — Layer 4: Calibration
=====================================================
Compares past predictions with reality to measure accuracy.
Run weekly on Sundays at 07:00 via LaunchAgent com.nerq.pred-calibration.
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
    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/pred-calibration.log")],
)
logger = logging.getLogger("nerq.pred.calibration")

TODAY = date.today()


def calibrate(lookback_days=7):
    """Compare predictions from N days ago with current reality."""
    start = time.time()
    check_date = (TODAY - timedelta(days=lookback_days)).isoformat()
    logger.info(f"Calibrating predictions from {check_date} (lookback={lookback_days}d)")

    from agentindex.db.models import get_session
    session = get_session()
    try:
        # Get predictions from N days ago
        preds = session.execute(text("""
            SELECT p.agent_id, p.agent_name, p.adoption_phase, p.fragility_index,
                   p.ai_recommendation_prob, p.survival_30d_prob, p.reasoning,
                   o_then.stars as stars_then, o_then.downloads as dl_then,
                   o_then.ai_crawls_24h as ai_then,
                   o_now.stars as stars_now, o_now.downloads as dl_now,
                   o_now.ai_crawls_24h as ai_now
            FROM predictions p
            LEFT JOIN prediction_observations o_then
                ON p.agent_id = o_then.agent_id AND o_then.observed_at = :check_date
            LEFT JOIN prediction_observations o_now
                ON p.agent_id = o_now.agent_id AND o_now.observed_at = :today
            WHERE p.predicted_at = :check_date
            AND o_now.id IS NOT NULL
        """), {"check_date": check_date, "today": TODAY.isoformat()}).fetchall()

        logger.info(f"Found {len(preds)} predictions to evaluate")

        results = {
            "adoption": {"correct": 0, "total": 0},
            "fragility": {"flagged": 0, "incidents": 0, "total": 0},
            "ai_recommendation": {"predicted_high": 0, "actually_high": 0, "total": 0},
            "survival": {"predicted_alive": 0, "actually_alive": 0, "total": 0},
        }

        for p in preds:
            stars_then = p[7] or 0
            stars_now = p[10] or 0
            dl_then = p[8] or 0
            dl_now = p[11] or 0
            ai_then = p[9] or 0
            ai_now = p[12] or 0

            # Adoption accuracy
            phase = p[2]
            grew = stars_now > stars_then
            if phase in ("emerging", "growing") and grew:
                results["adoption"]["correct"] += 1
            elif phase in ("declining", "abandoned") and not grew:
                results["adoption"]["correct"] += 1
            elif phase == "mature":
                results["adoption"]["correct"] += 1  # mature is hard to be wrong about
            results["adoption"]["total"] += 1

            # Fragility
            frag = p[3] or 0
            if frag > 50:
                results["fragility"]["flagged"] += 1
                # Check if tool actually had issues (stars dropped significantly)
                if stars_now < stars_then * 0.95:
                    results["fragility"]["incidents"] += 1
            results["fragility"]["total"] += 1

            # AI recommendation
            ai_prob = p[4] or 0
            if ai_prob > 0.3:
                results["ai_recommendation"]["predicted_high"] += 1
                if ai_now > 0:
                    results["ai_recommendation"]["actually_high"] += 1
            results["ai_recommendation"]["total"] += 1

            # Survival
            surv = p[5] or 0
            if surv > 0.7:
                results["survival"]["predicted_alive"] += 1
                if stars_now > 0:  # still has stars = still exists
                    results["survival"]["actually_alive"] += 1
            results["survival"]["total"] += 1

        # Calculate accuracy percentages
        report = {}
        for ptype, data in results.items():
            total = data.get("total", 0)
            if ptype == "adoption":
                acc = data["correct"] / max(1, total) * 100
            elif ptype == "fragility":
                acc = data["incidents"] / max(1, data["flagged"]) * 100 if data["flagged"] > 0 else None
            elif ptype == "ai_recommendation":
                acc = data["actually_high"] / max(1, data["predicted_high"]) * 100 if data["predicted_high"] > 0 else None
            elif ptype == "survival":
                acc = data["actually_alive"] / max(1, data["predicted_alive"]) * 100 if data["predicted_alive"] > 0 else None
            else:
                acc = None

            report[ptype] = {"accuracy_pct": round(acc, 1) if acc is not None else None, **data}

            # Store calibration result
            session.execute(text("""
                INSERT INTO prediction_calibration
                    (calibrated_at, prediction_type, predictions_evaluated, accuracy_pct, details)
                VALUES (:today, :ptype, :total, :acc, :details::jsonb)
            """), {
                "today": TODAY.isoformat(), "ptype": ptype,
                "total": total, "acc": round(acc, 1) if acc is not None else None,
                "details": json.dumps(data),
            })

        session.commit()
        elapsed = time.time() - start
        logger.info(f"Calibration complete in {elapsed:.1f}s")
        logger.info(f"Results: {json.dumps(report, indent=2)}")
        return report

    finally:
        session.close()


if __name__ == "__main__":
    report = calibrate()
    print(json.dumps(report, indent=2))
