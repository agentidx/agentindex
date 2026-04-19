#!/usr/bin/env python3
"""smedjan-reclaim — return orphaned in_progress tasks to the queue.

Triggered every 10 minutes by a LaunchAgent on Mac Studio (the host
that runs workers). Uses the criteria in factory_core.reclaim_stuck_tasks:
claim older than 30 min AND worker heartbeat older than 5 min (or
never).

Logs to ~/smedjan/worker-logs/reclaim.log and ntfies when any task is
reclaimed.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smedjan import factory_core, ntfy  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smedjan.reclaim")


def main() -> int:
    ttl = int(os.environ.get("SMEDJAN_RECLAIM_TTL_MIN", "30"))
    hb  = int(os.environ.get("SMEDJAN_RECLAIM_HEARTBEAT_MIN", "5"))
    reclaimed = factory_core.reclaim_stuck_tasks(
        claim_ttl_minutes=ttl,
        heartbeat_timeout_minutes=hb,
    )
    if reclaimed:
        lines = [f"{r['id']} ({r['title'][:60]})" for r in reclaimed]
        ntfy.push(
            f"[SMEDJAN] reclaim — {len(reclaimed)} task(s) returned to queue",
            "\n".join(lines),
            priority="default",
            tags="arrows_counterclockwise",
        )
    log.info("reclaim cycle: %d task(s) returned", len(reclaimed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
