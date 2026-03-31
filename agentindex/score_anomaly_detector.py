#!/usr/bin/env python3
"""
Score Anomaly Detector (D4)
============================
Runs daily at 06:30 via LaunchAgent com.zarq.anomaly-detector.
Compares current Vitality Scores and NDD alert levels against previous
values, flags significant changes, generates insight text, and optionally
posts a summary to Bluesky.

Exit 0 on success.
"""

import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LOG_PATH = "/tmp/anomaly-detector.log"
SCRIPT_DIR = Path(__file__).parent
STATE_PATH = SCRIPT_DIR / "anomaly_detector_state.json"
ANOMALIES_PATH = SCRIPT_DIR / "score_anomalies.json"
RISK_DB = str(SCRIPT_DIR / "crypto" / "crypto_trust.db")

# Thresholds
VITALITY_THRESHOLD = 10    # Flag if vitality changed by >10 points
VITALITY_SEVERE = 15       # Severe if >15 points
AGENT_TRUST_THRESHOLD = 15 # Flag if agent trust changed >15 points
BLUESKY_TRIGGER = 3        # Auto-post if >= 3 tokens changed by >15 points

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("anomaly-detector")


def load_state() -> dict:
    """Load previous state (vitality scores + NDD alert levels)."""
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict):
    """Save current state for next run."""
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)


def get_current_vitality() -> dict:
    """Get current vitality scores from DB."""
    try:
        conn = sqlite3.connect(RISK_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT token_id, symbol, name, vitality_score, vitality_grade,
                   ecosystem_gravity, capital_commitment, coordination_efficiency,
                   stress_resilience, organic_momentum
            FROM vitality_scores
        """).fetchall()
        conn.close()
        return {r["token_id"]: dict(r) for r in rows}
    except Exception as e:
        logger.warning("Failed to load vitality scores: %s", e)
        return {}


def get_current_ndd_alerts() -> dict:
    """Get current NDD alert levels from DB."""
    try:
        conn = sqlite3.connect(RISK_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT token_id, symbol, name, alert_level, ndd, ndd_trend,
                   crash_probability, trust_grade
            FROM crypto_ndd_daily
            WHERE (token_id, run_date) IN (
                SELECT token_id, MAX(run_date) FROM crypto_ndd_daily GROUP BY token_id
            )
        """).fetchall()
        conn.close()
        return {r["token_id"]: dict(r) for r in rows}
    except Exception as e:
        logger.warning("Failed to load NDD alerts: %s", e)
        return {}


def generate_vitality_insight(token_id: str, prev: dict, curr: dict) -> str:
    """Generate a short insight for a vitality score change."""
    name = curr.get("name") or curr.get("symbol") or token_id
    prev_score = prev.get("vitality_score", 0)
    curr_score = curr.get("vitality_score", 0)
    delta = curr_score - prev_score
    direction = "rose" if delta > 0 else "dropped"

    # Find which dimension changed the most
    dimensions = {
        "Ecosystem Gravity": ("ecosystem_gravity", prev.get("ecosystem_gravity"), curr.get("ecosystem_gravity")),
        "Capital Commitment": ("capital_commitment", prev.get("capital_commitment"), curr.get("capital_commitment")),
        "Coordination Efficiency": ("coordination_efficiency", prev.get("coordination_efficiency"), curr.get("coordination_efficiency")),
        "Stress Resilience": ("stress_resilience", prev.get("stress_resilience"), curr.get("stress_resilience")),
        "Organic Momentum": ("organic_momentum", prev.get("organic_momentum"), curr.get("organic_momentum")),
    }

    biggest_driver = None
    biggest_delta = 0
    for dim_name, (key, pv, cv) in dimensions.items():
        if pv is not None and cv is not None:
            d = abs(cv - pv)
            if d > biggest_delta:
                biggest_delta = d
                biggest_driver = dim_name
                driver_direction = "decline" if cv < pv else "improvement"

    insight = f"{name} Vitality Score {direction} {abs(delta):.1f} points ({prev_score:.1f}→{curr_score:.1f})"
    if biggest_driver and biggest_delta > 3:
        insight += f" driven by {biggest_driver} {driver_direction}."
    else:
        insight += "."

    return insight


def generate_alert_insight(token_id: str, prev_level: str, curr_data: dict) -> str:
    """Generate insight for NDD alert level change."""
    name = curr_data.get("name") or curr_data.get("symbol") or token_id
    curr_level = curr_data.get("alert_level", "UNKNOWN")
    ndd = curr_data.get("ndd")
    ndd_str = f" NDD={ndd:.2f}" if ndd else ""

    # Severity ordering
    severity = {"SAFE": 0, "WATCH": 1, "WARNING": 2, "DISTRESS": 3, "CRITICAL": 4}
    prev_sev = severity.get(prev_level, -1)
    curr_sev = severity.get(curr_level, -1)

    if curr_sev > prev_sev:
        return f"{name} alert escalated {prev_level}→{curr_level}.{ndd_str} Risk increasing."
    else:
        return f"{name} alert improved {prev_level}→{curr_level}.{ndd_str} Conditions stabilizing."


def post_bluesky_summary(anomalies: list[dict]):
    """Post a summary of significant anomalies to Bluesky."""
    try:
        from agentindex.bluesky_bot import post_to_bluesky
    except Exception as e:
        logger.warning("Cannot import bluesky_bot: %s", e)
        return

    severe = [a for a in anomalies if a.get("severity") == "severe"]
    if len(severe) < BLUESKY_TRIGGER:
        logger.info("Only %d severe anomalies (threshold=%d) — skipping Bluesky post", len(severe), BLUESKY_TRIGGER)
        return

    # Build post
    top = severe[:5]
    lines = [f"ZARQ Anomaly Alert — {len(severe)} significant score changes detected:\n"]
    for a in top:
        token = a.get("token_id", "?")
        delta = a.get("delta", 0)
        sign = "+" if delta > 0 else ""
        lines.append(f"• {token}: {sign}{delta:.0f}pts")

    text = "\n".join(lines)
    if len(severe) > 5:
        text += f"\n+{len(severe)-5} more"
    text += "\n\nFull report: zarq.ai/vitality"

    result = post_to_bluesky(text)
    if result:
        logger.info("Bluesky post created: %s", result.get("uri", ""))
    else:
        logger.warning("Bluesky post failed or disabled")


def main():
    t0 = time.time()
    now = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("Score Anomaly Detector started at %s", now.isoformat())

    # Load previous state
    prev_state = load_state()
    prev_vitality = prev_state.get("vitality", {})
    prev_alerts = prev_state.get("ndd_alerts", {})
    is_baseline = not prev_vitality
    if is_baseline:
        logger.info("No previous state — establishing baseline")

    # Get current data
    curr_vitality = get_current_vitality()
    curr_alerts = get_current_ndd_alerts()
    logger.info("Current: %d vitality scores, %d NDD records", len(curr_vitality), len(curr_alerts))

    anomalies = []

    if not is_baseline:
        # Compare vitality scores
        for token_id, curr in curr_vitality.items():
            prev = prev_vitality.get(token_id)
            if not prev:
                continue

            prev_score = prev.get("vitality_score", 0)
            curr_score = curr.get("vitality_score", 0)
            delta = curr_score - prev_score

            if abs(delta) > VITALITY_THRESHOLD:
                severity = "severe" if abs(delta) > VITALITY_SEVERE else "moderate"
                insight = generate_vitality_insight(token_id, prev, curr)
                anomalies.append({
                    "type": "vitality_change",
                    "token_id": token_id,
                    "symbol": curr.get("symbol"),
                    "name": curr.get("name"),
                    "prev_score": prev_score,
                    "curr_score": curr_score,
                    "delta": delta,
                    "severity": severity,
                    "insight": insight,
                    "detected_at": now.isoformat(),
                })

        # Compare NDD alert levels
        for token_id, curr_data in curr_alerts.items():
            prev_level = prev_alerts.get(token_id, {}).get("alert_level")
            curr_level = curr_data.get("alert_level")

            if prev_level and curr_level and prev_level != curr_level:
                insight = generate_alert_insight(token_id, prev_level, curr_data)
                anomalies.append({
                    "type": "alert_level_change",
                    "token_id": token_id,
                    "symbol": curr_data.get("symbol"),
                    "name": curr_data.get("name"),
                    "prev_level": prev_level,
                    "curr_level": curr_level,
                    "severity": "severe" if curr_level in ("CRITICAL", "DISTRESS") else "moderate",
                    "insight": insight,
                    "detected_at": now.isoformat(),
                })

    # Save anomalies
    anomalies.sort(key=lambda a: abs(a.get("delta", 0)), reverse=True)
    with open(ANOMALIES_PATH, "w") as f:
        json.dump({
            "generated_at": now.isoformat(),
            "is_baseline": is_baseline,
            "total_anomalies": len(anomalies),
            "severe_count": sum(1 for a in anomalies if a.get("severity") == "severe"),
            "anomalies": anomalies,
        }, f, indent=2)

    # Save current state as baseline for next run
    # Store compact form: just scores and alert levels
    new_state = {
        "last_run": now.isoformat(),
        "vitality": {
            tid: {
                "vitality_score": v["vitality_score"],
                "ecosystem_gravity": v.get("ecosystem_gravity"),
                "capital_commitment": v.get("capital_commitment"),
                "coordination_efficiency": v.get("coordination_efficiency"),
                "stress_resilience": v.get("stress_resilience"),
                "organic_momentum": v.get("organic_momentum"),
            }
            for tid, v in curr_vitality.items()
        },
        "ndd_alerts": {
            tid: {"alert_level": d.get("alert_level")}
            for tid, d in curr_alerts.items()
        },
    }
    save_state(new_state)

    # Post to Bluesky if significant
    if not is_baseline and anomalies:
        post_bluesky_summary(anomalies)

    # Summary
    severe = sum(1 for a in anomalies if a.get("severity") == "severe")
    moderate = sum(1 for a in anomalies if a.get("severity") == "moderate")
    vitality_changes = sum(1 for a in anomalies if a["type"] == "vitality_change")
    alert_changes = sum(1 for a in anomalies if a["type"] == "alert_level_change")

    elapsed = time.time() - t0
    logger.info("-" * 60)
    logger.info("ANOMALY DETECTION COMPLETE")
    logger.info("  Baseline run:       %s", "Yes" if is_baseline else "No")
    logger.info("  Total anomalies:    %d", len(anomalies))
    logger.info("  Severe:             %d", severe)
    logger.info("  Moderate:           %d", moderate)
    logger.info("  Vitality changes:   %d", vitality_changes)
    logger.info("  Alert changes:      %d", alert_changes)
    if anomalies and not is_baseline:
        logger.info("  Top anomalies:")
        for a in anomalies[:10]:
            logger.info("    %s", a["insight"])
    logger.info("  Elapsed:            %.1fs", elapsed)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
