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

from smedjan import factory_core  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smedjan.reclaim")


def main() -> int:
    ttl = int(os.environ.get("SMEDJAN_RECLAIM_TTL_MIN", "30"))
    hb  = int(os.environ.get("SMEDJAN_RECLAIM_HEARTBEAT_MIN", "5"))
    reclaimed = factory_core.reclaim_stuck_tasks(
        claim_ttl_minutes=ttl,
        heartbeat_timeout_minutes=hb,
    )
    # Reclaim is normal plumbing — restarts, SIGKILLs, flaps. Log it and
    # let the dashboard surface it. ntfy only fires on the dead-worker +
    # reclaim-failed combination, and that check lives in the canary /
    # watchdog path, not here.
    if reclaimed:
        ids = ", ".join(r["id"] for r in reclaimed)
        log.info("reclaim cycle: %d task(s) returned (%s)", len(reclaimed), ids)
    else:
        log.info("reclaim cycle: 0 task(s) returned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
