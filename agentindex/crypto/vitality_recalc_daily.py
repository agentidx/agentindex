#!/usr/bin/env python3
"""
ZARQ Vitality Score Daily Recalculation (D1)
=============================================
Runs daily at 06:00 via LaunchAgent com.zarq.vitality-recalc.
Recalculates Vitality Scores for ALL tokens using latest data,
then updates the vitality_scores table.

Exit 0 on success.
"""

import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agentindex.crypto.vitality_score import (
    DB_PATH,
    compute_vitality_scores,
    save_vitality_scores,
)

LOG_PATH = "/tmp/vitality-recalc.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("vitality-recalc")


def load_previous_scores() -> dict[str, float]:
    """Load current vitality scores for change detection."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        rows = conn.execute("SELECT token_id, vitality_score FROM vitality_scores").fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def main():
    t0 = time.time()
    now = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("Vitality Score recalculation started at %s", now.isoformat())

    # Load previous scores for comparison
    prev = load_previous_scores()
    logger.info("Previous scores loaded: %d tokens", len(prev))

    # Recalculate all vitality scores
    try:
        results = compute_vitality_scores()
    except Exception as e:
        logger.error("compute_vitality_scores() failed: %s", e, exc_info=True)
        return 1

    if not results:
        logger.warning("No vitality scores computed — something is wrong")
        return 1

    # Save to database
    try:
        save_vitality_scores(results)
    except Exception as e:
        logger.error("save_vitality_scores() failed: %s", e, exc_info=True)
        return 1

    # Change analysis
    new_scores = {r["token_id"]: r["vitality_score"] for r in results}
    changed_5 = 0
    changed_10 = 0
    new_tokens = 0
    removed_tokens = 0

    for tid, score in new_scores.items():
        if tid in prev:
            delta = abs(score - prev[tid])
            if delta > 5:
                changed_5 += 1
            if delta > 10:
                changed_10 += 1
        else:
            new_tokens += 1

    for tid in prev:
        if tid not in new_scores:
            removed_tokens += 1

    elapsed = time.time() - t0

    # Grade distribution
    grades = {}
    for r in results:
        g = r["vitality_grade"]
        grades[g] = grades.get(g, 0) + 1

    logger.info("-" * 60)
    logger.info("RECALCULATION COMPLETE")
    logger.info("  Tokens scored:     %d", len(results))
    logger.info("  Previous count:    %d", len(prev))
    logger.info("  Changed >5 pts:    %d", changed_5)
    logger.info("  Changed >10 pts:   %d", changed_10)
    logger.info("  New tokens:        %d", new_tokens)
    logger.info("  Removed tokens:    %d", removed_tokens)
    logger.info("  Grade distribution: %s", grades)
    logger.info("  Elapsed:           %.1fs", elapsed)
    logger.info("  Timestamp:         %s", now.isoformat())
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
