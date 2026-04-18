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
from pathlib import Path
from urllib.parse import unquote

import redis

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smedjan import sources  # noqa: E402

REGISTRIES = [s.strip() for s in os.environ.get("SMEDJAN_CANARY_REGS", "gems,homebrew").split(",") if s.strip()]
DRY_RUN = os.environ.get("SMEDJAN_DRY_RUN") == "1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smedjan.purge_redis")


def main() -> int:
    slugs: set[str] = set()
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT slug FROM public.software_registry "
            "WHERE registry = ANY(%s) AND enriched_at IS NOT NULL",
            (REGISTRIES,),
        )
        slugs = {r[0].lower() for r in cur.fetchall()}
    log.info("loaded %d slugs for %s", len(slugs), REGISTRIES)

    r = redis.Redis(host="127.0.0.1", port=6379, db=1, socket_timeout=5)
    r.ping()

    total_scanned = 0
    matched = 0
    deleted = 0
    for key in r.scan_iter(match="pc:/safe/*", count=500):
        total_scanned += 1
        k = key.decode() if isinstance(key, bytes) else key
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
    log.info("scanned %d, matched %d canary keys, deleted %d (dry_run=%s)",
             total_scanned, matched, deleted, DRY_RUN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
