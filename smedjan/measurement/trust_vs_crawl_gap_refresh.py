"""
Refresh the snapshot tables that back ``smedjan.trust_vs_crawl_gap``.

Two writes per run:

1. ``smedjan.trust_score_top_n_snapshot`` — top-N (default 1000) entities
   by ``trust_score_v2`` from the Nerq RO replica's
   ``public.entity_lookup``. Rank-based, not threshold-based, because the
   audit framing ("top-1000 trust × top-2000 crawled") is a ranked
   intersection and FU-CITATION-20260422-03 is the companion view.

2. ``smedjan.sitemap_entity_snapshot`` — live entity-sitemap membership,
   built by fetching /sitemap-safe-{0..5}.xml, /sitemap-agents-{0..5}.xml
   and /sitemap-mcp.xml from nerq.ai and extracting the slug portion of
   every ``<loc>`` URL. We snapshot the state so the view can join on it
   instead of issuing HTTP fetches per query.

Both tables are swapped atomically via staging temp tables + TRUNCATE +
INSERT so readers never observe a half-populated snapshot.

Invocation
----------
Run as ``python3 -m smedjan.measurement.trust_vs_crawl_gap_refresh``.
Intended to be wired into the nightly timer alongside
``trust_crawl_coverage_refresh`` — both feed the FU-CITATION
measurement surface.

Source: FU-CITATION-20260422-03.
"""
from __future__ import annotations

import logging
import re
import sys
import urllib.request
from datetime import datetime, timezone

from psycopg2.extras import execute_values

from smedjan.sources import nerq_readonly_cursor, smedjan_db_cursor

log = logging.getLogger("smedjan.measurement.trust_vs_crawl_gap_refresh")

TOP_N = 1000
SITEMAP_CHUNKS = {
    "safe":  [f"https://nerq.ai/sitemap-safe-{i}.xml"   for i in range(6)],
    "agent": [f"https://nerq.ai/sitemap-agents-{i}.xml" for i in range(6)],
    "mcp":   ["https://nerq.ai/sitemap-mcp.xml"],
}
HTTP_TIMEOUT = 30
UA = "SmedjanAudit/1.0 (FU-CITATION-20260422-03)"

# Slug portion of an entity URL.
_ENTITY_LOC_RE = re.compile(r"<loc>\s*https://nerq\.ai/(?:agent|safe|mcp)/([^<\s?#]+)\s*</loc>", re.I)


def _fetch_top_n_from_nerq(n: int) -> list[tuple[int, str, float, str | None, str | None, str | None]]:
    """Return ``[(trust_rank, slug, trust_score_v2, trust_grade, category, source), ...]``
    ordered by ``trust_score_v2`` DESC, with ``trust_rank`` 1-based.

    ``public.entity_lookup`` has duplicate slugs across sources
    (e.g. ``a2a`` appears on github, npm, huggingface_full). We collapse
    client-side to one row per slug, keeping the highest-scoring variant,
    which matches the audit's "DISTINCT slug ORDER BY trust_score_v2
    DESC" framing. Client-side dedupe is used instead of a SQL window
    function so the query can use ``idx_el_score_v2`` — the window
    variant triggered a 60s statement-timeout against the 5M-row table.
    We over-fetch by 10× then take the first N distinct slugs.
    """
    fetch_limit = max(n * 10, 5000)
    with nerq_readonly_cursor() as (_, cur):
        cur.execute(
            """
            SELECT slug, trust_score_v2, trust_grade, category, source
              FROM public.entity_lookup
             WHERE slug IS NOT NULL
               AND trust_score_v2 IS NOT NULL
             ORDER BY trust_score_v2 DESC NULLS LAST
             LIMIT %s
            """,
            (fetch_limit,),
        )
        rows = cur.fetchall()

    seen: set[str] = set()
    out: list[tuple[int, str, float, str | None, str | None, str | None]] = []
    rank = 0
    for slug, score, grade, category, source in rows:
        if slug in seen:
            continue
        seen.add(slug)
        rank += 1
        out.append((rank, slug, score, grade, category, source))
        if rank >= n:
            break
    return out


def _swap_trust_snapshot(
    rows: list[tuple[int, str, float, str | None, str | None, str | None]],
) -> int:
    now = datetime.now(timezone.utc)
    with smedjan_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TEMP TABLE _tstn_staging
              (LIKE smedjan.trust_score_top_n_snapshot)
            ON COMMIT DROP
            """
        )
        execute_values(
            cur,
            """
            INSERT INTO _tstn_staging
                (trust_rank, slug, trust_score_v2, trust_grade, category, source, snapshot_at)
            VALUES %s
            """,
            [(rank, slug, score, grade, cat, src, now)
             for rank, slug, score, grade, cat, src in rows],
            page_size=500,
        )
        cur.execute("TRUNCATE smedjan.trust_score_top_n_snapshot")
        cur.execute(
            """
            INSERT INTO smedjan.trust_score_top_n_snapshot
                (trust_rank, slug, trust_score_v2, trust_grade, category, source, snapshot_at)
            SELECT trust_rank, slug, trust_score_v2, trust_grade, category, source, snapshot_at
              FROM _tstn_staging
            """
        )
        cur.execute("SELECT count(*) FROM smedjan.trust_score_top_n_snapshot")
        (written,) = cur.fetchone()
        return int(written)


def _fetch_sitemap_slugs() -> list[tuple[str, str]]:
    """Return ``[(slug, sitemap_family), ...]`` parsed from live nerq.ai."""
    out: list[tuple[str, str]] = []
    for family, urls in SITEMAP_CHUNKS.items():
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
            except Exception as e:
                log.warning("sitemap fetch failed for %s: %s", url, e)
                continue
            for m in _ENTITY_LOC_RE.finditer(body):
                slug = m.group(1).strip()
                if slug:
                    out.append((slug, family))
    # Dedupe (slug, family) in case a chunk repeats.
    return sorted(set(out))


def _swap_sitemap_snapshot(rows: list[tuple[str, str]]) -> int:
    now = datetime.now(timezone.utc)
    with smedjan_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TEMP TABLE _ses_staging
              (LIKE smedjan.sitemap_entity_snapshot)
            ON COMMIT DROP
            """
        )
        execute_values(
            cur,
            """
            INSERT INTO _ses_staging (slug, sitemap_family, snapshot_at)
            VALUES %s
            """,
            [(slug, family, now) for slug, family in rows],
            page_size=2000,
        )
        cur.execute("TRUNCATE smedjan.sitemap_entity_snapshot")
        cur.execute(
            """
            INSERT INTO smedjan.sitemap_entity_snapshot (slug, sitemap_family, snapshot_at)
            SELECT slug, sitemap_family, snapshot_at FROM _ses_staging
            """
        )
        cur.execute("SELECT count(*) FROM smedjan.sitemap_entity_snapshot")
        (written,) = cur.fetchone()
        return int(written)


def refresh() -> dict:
    trust_rows = _fetch_top_n_from_nerq(TOP_N)
    trust_written = _swap_trust_snapshot(trust_rows)

    sitemap_rows = _fetch_sitemap_slugs()
    sitemap_written = _swap_sitemap_snapshot(sitemap_rows)

    return {
        "top_n": TOP_N,
        "trust_pulled": len(trust_rows),
        "trust_written": trust_written,
        "sitemap_pulled": len(sitemap_rows),
        "sitemap_written": sitemap_written,
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        summary = refresh()
    except Exception as e:  # noqa: BLE001 — top-level guard for systemd
        log.exception("trust_vs_crawl_gap_refresh failed: %s", e)
        return 1
    print(
        f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
        f"trust_vs_crawl_gap_refresh: {summary}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
