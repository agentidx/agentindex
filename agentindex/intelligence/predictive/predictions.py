#!/usr/bin/env python3
"""
Nerq Predictive Intelligence — Layer 3: Composite Predictions
==============================================================
Generates adoption phase, fragility, AI recommendation, survival predictions.
Run daily at 06:00 via LaunchAgent com.nerq.pred-predictions.
"""

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agentindex.db.models import get_db_session
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-6s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/pred-predictions.log")],
)
logger = logging.getLogger("nerq.pred.predictions")

TODAY = date.today()


def predict_adoption_phase(s):
    stars = s.get("stars") or 0
    star_vel = s.get("star_velocity_7d") or 0
    star_accel = s.get("star_acceleration") or 0
    commit_fresh = s.get("commit_freshness_days") or 999

    if star_accel > 0 and stars < 1000:
        return "emerging", min(0.8, 0.5 + star_accel / 100), "Early stage with accelerating growth"
    elif star_accel > 0 and stars >= 1000:
        return "growing", min(0.9, 0.6 + star_accel / 200), "Established and still accelerating"
    elif star_accel <= 0 and star_vel > 0:
        return "mature", 0.7, "Growth slowing but still positive"
    elif star_vel <= 0 and commit_fresh < 60:
        return "declining", 0.6, "Negative growth but still maintained"
    else:
        return "abandoned", 0.5 if commit_fresh > 180 else 0.4, "No growth, no recent maintenance"


def predict_fragility(s):
    fragility = 0
    reasons = []
    stars = s.get("stars") or 0
    downloads = s.get("downloads") or 0
    bus = s.get("bus_factor") or 1
    irr = s.get("issue_resolution_rate") or 0.5
    breadth = s.get("ecosystem_breadth") or 1
    star_accel = s.get("star_acceleration") or 0
    commit_fresh = s.get("commit_freshness_days") or 999

    if bus <= 1 and downloads > 10000:
        fragility += 30
        reasons.append("Single maintainer with large user base")
    if star_accel > 50 and irr < 0.3:
        fragility += 20
        reasons.append("Fast growth without proportional issue resolution")
    if commit_fresh > 90:
        fragility += 15
        reasons.append(f"No commits in {commit_fresh} days")
    if breadth == 1:
        fragility += 10
        reasons.append("Single ecosystem distribution")
    if stars > 5000 and bus < 3:
        fragility += 15
        reasons.append("Popular project with few contributors")

    return min(100, fragility), "; ".join(reasons) if reasons else "No significant fragility signals"


def predict_ai_recommendation(s):
    ai_score = s.get("ai_attention_score") or 0
    ai_delta = s.get("ai_attention_delta_7d") or 0
    trust = s.get("trust_score") or 50
    human = s.get("human_visits") or 0

    base_prob = min(1.0, ai_score / 50) if ai_score > 0 else 0.05
    if ai_delta > 0:
        base_prob = min(1.0, base_prob * 1.3)
    trust_factor = trust / 100 if trust else 0.5
    pop_factor = min(1.5, 1.0 + human / 100) if human > 0 else 1.0

    return min(1.0, base_prob * trust_factor * pop_factor)


def predict_survival_30d(s):
    stars = s.get("stars") or 0
    star_vel = s.get("star_velocity_7d") or 0
    irr = s.get("issue_resolution_rate") or 0.5
    bus = s.get("bus_factor") or 1
    commit_fresh = s.get("commit_freshness_days") or 999

    # Base rate by star level
    if stars > 10000:
        base = 0.98
    elif stars > 1000:
        base = 0.95
    elif stars > 100:
        base = 0.90
    elif stars > 10:
        base = 0.80
    else:
        base = 0.60

    if commit_fresh > 180:
        base *= 0.5
    elif commit_fresh > 90:
        base *= 0.7
    if irr > 0.5:
        base *= 1.05
    if star_vel > 0:
        base *= 1.03
    if bus == 1:
        base *= 0.9

    return min(1.0, max(0.01, base))


def generate_predictions():
    start = time.time()
    logger.info(f"Generating predictions for {TODAY}")

    from agentindex.db.models import get_session
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT agent_id, agent_name, signals_json
            FROM prediction_signals
            WHERE calculated_at = :today
        """), {"today": TODAY.isoformat()}).fetchall()

        logger.info(f"Found {len(rows)} agents with signals")
        inserted = 0

        for agent_id, agent_name, signals_json in rows:
            try:
                s = json.loads(signals_json) if isinstance(signals_json, str) else (signals_json if signals_json else {})
                if not s:
                    continue

                phase, phase_conf, phase_reason = predict_adoption_phase(s)
                frag, frag_reason = predict_fragility(s)
                ai_prob = predict_ai_recommendation(s)
                surv = predict_survival_30d(s)

                # Composite NPI
                phase_score = {"emerging": 70, "growing": 90, "mature": 60, "declining": 30, "abandoned": 10}.get(phase, 50)
                npi = (
                    phase_score * 0.25 +
                    (100 - frag) * 0.25 +
                    ai_prob * 100 * 0.25 +
                    surv * 100 * 0.25
                )

                reasoning = {
                    "adoption": {"phase": phase, "confidence": round(phase_conf, 2), "reason": phase_reason},
                    "fragility": {"index": round(frag, 1), "reason": frag_reason},
                    "ai_recommendation": {"probability": round(ai_prob, 3)},
                    "survival_30d": {"probability": round(surv, 3)},
                    "signals_summary": {
                        "stars": s.get("stars"), "star_velocity": s.get("star_velocity_7d"),
                        "ai_attention": s.get("ai_attention_score"),
                        "trust_score": s.get("trust_score"),
                    },
                }

                session.execute(text("""
                    INSERT INTO predictions
                        (agent_id, agent_name, predicted_at, adoption_phase, adoption_confidence,
                         fragility_index, fragility_reasoning, ai_recommendation_prob,
                         survival_30d_prob, nerq_predictive_index, reasoning)
                    VALUES
                        (:aid, :name, :today, :phase, :conf, :frag, :frag_r, :ai_prob,
                         :surv, :npi, CAST(:reasoning AS jsonb))
                    ON CONFLICT (agent_id, predicted_at) DO UPDATE SET
                        nerq_predictive_index = EXCLUDED.nerq_predictive_index,
                        reasoning = EXCLUDED.reasoning
                """), {
                    "aid": str(agent_id), "name": agent_name, "today": TODAY.isoformat(),
                    "phase": phase, "conf": round(phase_conf, 2),
                    "frag": round(frag, 1), "frag_r": frag_reason,
                    "ai_prob": round(ai_prob, 3), "surv": round(surv, 3),
                    "npi": round(npi, 1), "reasoning": json.dumps(reasoning),
                })
                inserted += 1

                if inserted % 500 == 0:
                    session.commit()
                    logger.info(f"  Generated {inserted} predictions...")

            except Exception as e:
                logger.warning(f"Prediction failed for {agent_name}: {e}")
                session.rollback()

        session.commit()
        elapsed = time.time() - start
        logger.info(f"Prediction generation complete: {inserted} predictions, {elapsed:.1f}s")
        return inserted

    finally:
        session.close()


if __name__ == "__main__":
    count = generate_predictions()
    print(f"Generated {count} predictions for {TODAY}")
