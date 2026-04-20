#!/usr/bin/env python3
"""
T302 — sameAs/Wikidata skeleton for top-N Smedjan slugs.

For the top-N slugs ranked by smedjan.ai_demand_scores.score, look up a
Wikidata QID via the free wbsearchentities endpoint and persist the
result (hit or miss) in smedjan.wikidata_lookup. The cache is consumed
by agentindex.agent_safety_pages, which adds the resolved Wikidata URI
to the entity JSON-LD `sameAs` array.

No credentials required (Wikidata is unauthenticated, free-tier).

Run:
    python3 -m smedjan.scripts.wikidata_lookup            # default top-100
    python3 -m smedjan.scripts.wikidata_lookup --top-n 250
    python3 -m smedjan.scripts.wikidata_lookup --refresh-misses
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import urllib.parse
import urllib.request
from typing import Optional

from smedjan.sources import smedjan_db_cursor

log = logging.getLogger("smedjan.wikidata_lookup")

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "smedjan-wikidata-lookup/0.1 (+https://nerq.ai; ops@nerq.ai)"
WIKIDATA_ENTITY_PREFIX = "https://www.wikidata.org/entity/"


DDL = """
CREATE TABLE IF NOT EXISTS smedjan.wikidata_lookup (
    slug          text        PRIMARY KEY,
    qid           text,
    entity_label  text,
    entity_url    text,
    description   text,
    source_term   text        NOT NULL,
    looked_up_at  timestamptz NOT NULL DEFAULT now(),
    is_miss       boolean     NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_wikidata_lookup_qid
    ON smedjan.wikidata_lookup (qid)
    WHERE qid IS NOT NULL;
"""


def ensure_table() -> None:
    with smedjan_db_cursor() as (_, cur):
        cur.execute(DDL)


def fetch_top_slugs(top_n: int) -> list[str]:
    with smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug FROM smedjan.ai_demand_scores "
            "WHERE score IS NOT NULL "
            "ORDER BY score DESC, slug ASC LIMIT %s",
            (top_n,),
        )
        return [r[0] for r in cur.fetchall()]


def already_resolved(slugs: list[str], include_misses: bool) -> set[str]:
    """Return the subset of `slugs` that already have a row in the cache."""
    if not slugs:
        return set()
    with smedjan_db_cursor() as (_, cur):
        if include_misses:
            cur.execute(
                "SELECT slug FROM smedjan.wikidata_lookup WHERE slug = ANY(%s)",
                (slugs,),
            )
        else:
            cur.execute(
                "SELECT slug FROM smedjan.wikidata_lookup "
                "WHERE slug = ANY(%s) AND is_miss = false",
                (slugs,),
            )
        return {r[0] for r in cur.fetchall()}


def slug_to_search_term(slug: str) -> str:
    return slug.replace("-", " ").strip()


def wikidata_search(term: str, timeout: float = 10.0) -> Optional[dict]:
    """Return the top wbsearchentities hit for `term`, or None."""
    params = {
        "action": "wbsearchentities",
        "search": term,
        "language": "en",
        "type": "item",
        "limit": "1",
        "format": "json",
    }
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        import json as _json
        data = _json.loads(resp.read().decode("utf-8"))
    hits = data.get("search") or []
    return hits[0] if hits else None


def upsert_hit(slug: str, term: str, hit: dict) -> None:
    qid = hit.get("id")
    label = hit.get("label") or hit.get("display", {}).get("label", {}).get("value")
    desc = hit.get("description") or hit.get("display", {}).get("description", {}).get("value")
    entity_url = WIKIDATA_ENTITY_PREFIX + qid if qid else None
    with smedjan_db_cursor() as (_, cur):
        cur.execute(
            """
            INSERT INTO smedjan.wikidata_lookup
                (slug, qid, entity_label, entity_url, description, source_term, looked_up_at, is_miss)
            VALUES (%s, %s, %s, %s, %s, %s, now(), false)
            ON CONFLICT (slug) DO UPDATE SET
                qid = EXCLUDED.qid,
                entity_label = EXCLUDED.entity_label,
                entity_url = EXCLUDED.entity_url,
                description = EXCLUDED.description,
                source_term = EXCLUDED.source_term,
                looked_up_at = now(),
                is_miss = false
            """,
            (slug, qid, label, entity_url, desc, term),
        )


def upsert_miss(slug: str, term: str) -> None:
    with smedjan_db_cursor() as (_, cur):
        cur.execute(
            """
            INSERT INTO smedjan.wikidata_lookup
                (slug, qid, entity_label, entity_url, description, source_term, looked_up_at, is_miss)
            VALUES (%s, NULL, NULL, NULL, NULL, %s, now(), true)
            ON CONFLICT (slug) DO UPDATE SET
                source_term = EXCLUDED.source_term,
                looked_up_at = now(),
                is_miss = true
            """,
            (slug, term),
        )


def run(top_n: int, refresh_misses: bool, sleep_s: float) -> dict:
    ensure_table()
    slugs = fetch_top_slugs(top_n)
    if not slugs:
        log.warning("no slugs returned from smedjan.ai_demand_scores")
        return {"requested": 0, "skipped": 0, "hits": 0, "misses": 0, "errors": 0}

    skip = already_resolved(slugs, include_misses=not refresh_misses)
    todo = [s for s in slugs if s not in skip]

    log.info("top_n=%d already_cached=%d to_lookup=%d", len(slugs), len(skip), len(todo))

    hits = misses = errors = 0
    for i, slug in enumerate(todo, 1):
        term = slug_to_search_term(slug)
        try:
            hit = wikidata_search(term)
        except Exception as e:
            log.warning("[%d/%d] %s: lookup failed: %s", i, len(todo), slug, e)
            errors += 1
            time.sleep(sleep_s)
            continue
        if hit and hit.get("id"):
            upsert_hit(slug, term, hit)
            hits += 1
            log.info("[%d/%d] %s -> %s (%s)", i, len(todo), slug, hit["id"], hit.get("label"))
        else:
            upsert_miss(slug, term)
            misses += 1
            log.info("[%d/%d] %s -> MISS", i, len(todo), slug)
        time.sleep(sleep_s)

    return {
        "requested": len(slugs),
        "skipped": len(skip),
        "hits": hits,
        "misses": misses,
        "errors": errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-n", type=int, default=100)
    ap.add_argument("--refresh-misses", action="store_true",
                    help="re-look-up slugs previously recorded as misses")
    ap.add_argument("--sleep-seconds", type=float, default=0.2,
                    help="politeness delay between Wikidata calls")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    summary = run(args.top_n, args.refresh_misses, args.sleep_seconds)
    print(
        "wikidata_lookup: requested={requested} skipped={skipped} "
        "hits={hits} misses={misses} errors={errors}".format(**summary)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
