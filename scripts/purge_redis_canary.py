#!/usr/bin/env python3
"""
purge_redis_canary.py — delete Redis page-cache entries for the L1 canary
cohort so the new rendering (env var L1_UNLOCK_REGISTRIES=gems,homebrew)
takes effect immediately on the next request instead of waiting out the
4h TTL in `pc:*` cache at db=1.

Scope: keys matching `pc:/safe/<slug>*` (including language prefixes
and sub-routes) where <slug> is an enriched non-King in gems or homebrew.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import redis

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smedjan import sources  # noqa: E402

_raw_regs = os.environ.get("SMEDJAN_CANARY_REGS")
if _raw_regs is None or _raw_regs.strip() in ("", "*"):
    REGISTRIES: list[str] = []  # empty => full /safe/* purge (no slug filter)
    FULL_SCAN = True
else:
    REGISTRIES = [s.strip() for s in _raw_regs.split(",") if s.strip()]
    FULL_SCAN = False
DRY_RUN = os.environ.get("SMEDJAN_DRY_RUN") == "1"
DELETE_SLEEP_MS = int(os.environ.get("SMEDJAN_DELETE_SLEEP_MS", "0"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smedjan.purge_redis")


def main() -> int:
    slugs: set[str] = set()
    if not FULL_SCAN:
        with sources.nerq_readonly_cursor() as (_, cur):
            cur.execute(
                "SELECT slug FROM public.software_registry "
                "WHERE registry = ANY(%s) AND enriched_at IS NOT NULL",
                (REGISTRIES,),
            )
            slugs = {r[0].lower() for r in cur.fetchall()}
        log.info("loaded %d slugs for %s", len(slugs), REGISTRIES)
    else:
        log.info("FULL_SCAN mode: deleting every pc:/safe/* key (no slug filter) "
                 "with delete_sleep_ms=%d", DELETE_SLEEP_MS)

    r = redis.Redis(host="127.0.0.1", port=6379, db=1, socket_timeout=5)
    r.ping()

    sleep_sec = DELETE_SLEEP_MS / 1000.0
    total_scanned = 0
    matched = 0
    deleted = 0
    for key in r.scan_iter(match="pc:/safe/*", count=500):
        total_scanned += 1
        k = key.decode() if isinstance(key, bytes) else key
        if FULL_SCAN:
            matched += 1
            if not DRY_RUN:
                r.delete(key)
                deleted += 1
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
            if total_scanned % 500 == 0:
                log.info("progress scanned=%d deleted=%d", total_scanned, deleted)
            continue
        # pc:/safe/<slug> OR pc:/safe/<slug>/sub OR pc:/xx/safe/<slug>
        rest = k.split("pc:/", 1)[1]                 # safe/<slug>... OR en/safe/<slug>
        parts = rest.split("/")
        # drop language prefix if present
        if len(parts) >= 3 and len(parts[0]) == 2 and parts[1] == "safe":
            slug_candidate = parts[2]
        elif len(parts) >= 2 and parts[0] == "safe":
            slug_candidate = parts[1]
        else:
            continue
        slug_candidate = unquote(slug_candidate).lower()
        if slug_candidate in slugs:
            matched += 1
            if not DRY_RUN:
                r.delete(key)
                deleted += 1
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
    log.info("scanned %d, matched %d canary keys, deleted %d (dry_run=%s, full_scan=%s)",
             total_scanned, matched, deleted, DRY_RUN, FULL_SCAN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
