#!/usr/bin/env python3
"""Audit-query for conversion experiments shipped under POL-CONV-001.

POL-CONV-001 ("AI-cohort-first rollout rule", ~/smedjan/policies/
ai-cohort-first-rollout.md) requires experiments to emit
`?exp=<id>&v=<variant>&surf=<surface>` on every variant CTA. This helper
reads those back from analytics_mirror.requests and returns rows of
(exp_id, variant, visitor_type, surface, impressions).

Run directly for a human-readable table:

    PYTHONPATH=~/agentindex python -m smedjan.measurement.conversion_experiment_query
    PYTHONPATH=~/agentindex python -m smedjan.measurement.conversion_experiment_query --days 14 --exp fu-conversion-20260418-03
"""

from __future__ import annotations

import argparse
import sys

from smedjan import sources

_SQL = """
WITH labeled AS (
  SELECT
    ts,
    visitor_type,
    substring(query_string FROM 'exp=([a-z0-9_-]+)')     AS exp_id,
    substring(query_string FROM '[&?]v=([a-z])')         AS variant,
    coalesce(
      substring(query_string FROM '[&?]surf=([a-z]+)'),
      CASE
        WHEN path = '/'               THEN 'home'
        WHEN path LIKE '/dataset/%%'  THEN 'dataset'
        WHEN path LIKE '/model/%%'    THEN 'model'
        WHEN path LIKE '/safe/%%'     THEN 'safe'
        WHEN path LIKE '/profile/%%'  THEN 'profile'
        WHEN path LIKE '/agent/%%'    THEN 'agent'
        WHEN path LIKE '/compare/%%'  THEN 'compare'
        WHEN path LIKE '/zarq/%%'     THEN 'zarq'
        ELSE 'other'
      END
    ) AS surface
  FROM analytics_mirror.requests
  WHERE ts >= now() - (%(days)s::int * interval '1 day')
    AND query_string LIKE '%%exp=%%'
    AND status < 400
    AND method = 'GET'
)
SELECT exp_id, variant, visitor_type, surface, count(*) AS impressions
  FROM labeled
 WHERE exp_id IS NOT NULL
   AND (%(exp)s::text IS NULL OR exp_id = %(exp)s::text)
 GROUP BY 1,2,3,4
 ORDER BY 1,2,3,4
"""


def query(days: int = 30, exp_id: str | None = None) -> list[tuple]:
    """Return rows of (exp_id, variant, visitor_type, surface, impressions)."""
    with sources.analytics_mirror_cursor() as (_, cur):
        cur.execute(_SQL, {"days": days, "exp": exp_id})
        return cur.fetchall()


def _fmt(rows: list[tuple]) -> str:
    if not rows:
        return "(no experiment-tagged rows found — either no experiment is running, or the tagging in §3.a of POL-CONV-001 is missing)"
    header = f"{'exp_id':<40} {'v':<2} {'visitor_type':<14} {'surface':<10} {'impressions':>12}"
    lines = [header, "-" * len(header)]
    for exp, v, vt, surf, n in rows:
        lines.append(f"{(exp or ''):<40} {(v or ''):<2} {(vt or ''):<14} {(surf or ''):<10} {n:>12}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=30, help="lookback window (default 30)")
    ap.add_argument("--exp", default=None, help="filter to one experiment id")
    args = ap.parse_args(argv)
    rows = query(days=args.days, exp_id=args.exp)
    print(_fmt(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
