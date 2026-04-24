"""FU-CONVERSION-20260424-11 — Redefine citation_ratio_daily on a human-click basis.

Parent: AUDIT-CONVERSION-20260424 · Finding 11.

This script regenerates the evidence and the legacy-vs-new daily
comparison that back the proposal at:

    /Users/anstudio/smedjan/audit-reports/2026-04-24-FU-CONVERSION-20260424-11-ratio-redefinition.md

It is read-only — no view is created, replaced, or dropped. The
proposed SQL lives in the proposal markdown (and is also dropped at
`smedjan/measurement/citation_ratio_daily_v2.sql` as a candidate file
for the eventual cut-over PR).

Usage::

    PYTHONPATH=/Users/anstudio/agentindex-factory \\
        /Users/anstudio/agentindex/venv/bin/python3 \\
        /Users/anstudio/agentindex/smedjan/audits/FU-CONVERSION-20260424-11.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

from smedjan import sources

OUT_DIR = Path("/Users/anstudio/smedjan/audit-reports")
CSV_PATH = OUT_DIR / "2026-04-24-FU-CONVERSION-20260424-11-legacy-vs-new.csv"
PROPOSAL_PATH = OUT_DIR / "2026-04-24-FU-CONVERSION-20260424-11-ratio-redefinition.md"

# Engines included in the new "human click" predicate. Three of them
# (you.com, phind.com, copilot.microsoft.com) currently have zero hits
# in the 30-day mirror window; we include them for forward-compat.
NEW_ENGINES = (
    "chatgpt.com",
    "perplexity.ai",
    "claude.ai",
    "kagi.com",
    "you.com",
    "phind.com",
    "copilot.microsoft.com",
)


def diagnostics(cur) -> dict:
    """Pull the numbers the proposal relies on. Returns a JSON-serialisable dict."""
    out: dict = {}

    cur.execute(
        """
        SELECT count(*) FROM analytics_mirror.requests
         WHERE ts >= now() - interval '30 days'
           AND visitor_type = 'ai_mediated';
        """
    )
    out["legacy_ai_mediated_30d"] = cur.fetchone()[0]

    cur.execute(
        """
        SELECT count(*) FROM analytics_mirror.requests
         WHERE ts >= now() - interval '30 days'
           AND is_bot = 0
           AND ai_source IS NOT NULL AND ai_source <> '';
        """
    )
    out["audit_finding11_human_clicks_30d"] = cur.fetchone()[0]

    cur.execute(
        """
        SELECT count(*) FROM analytics_mirror.requests
         WHERE ts >= now() - interval '30 days'
           AND is_bot = 0
           AND referrer_domain = ANY(%s);
        """,
        (list(NEW_ENGINES),),
    )
    out["new_predicate_30d"] = cur.fetchone()[0]

    # Cross-tab — should show every ai_mediated row is is_bot=1.
    cur.execute(
        """
        SELECT is_bot, is_ai_bot, ai_source, count(*)
          FROM analytics_mirror.requests
         WHERE ts >= now() - interval '30 days'
           AND visitor_type = 'ai_mediated'
         GROUP BY 1, 2, 3 ORDER BY 4 DESC;
        """
    )
    out["legacy_crosstab"] = [
        {"is_bot": r[0], "is_ai_bot": r[1], "ai_source": r[2], "rows": r[3]}
        for r in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT referrer_domain, count(*)
          FROM analytics_mirror.requests
         WHERE ts >= now() - interval '30 days'
           AND is_bot = 0
           AND referrer_domain = ANY(%s)
         GROUP BY 1 ORDER BY 2 DESC;
        """,
        (list(NEW_ENGINES),),
    )
    out["new_predicate_by_engine"] = [
        {"engine": r[0], "rows": r[1]} for r in cur.fetchall()
    ]

    return out


def daily_comparison(cur) -> list[tuple]:
    cur.execute(
        """
        WITH days AS (
          SELECT generate_series(
                   (now() AT TIME ZONE 'UTC')::date - 29,
                   (now() AT TIME ZONE 'UTC')::date,
                   interval '1 day'
                 )::date AS day
        ),
        legacy AS (
          SELECT (ts AT TIME ZONE 'UTC')::date AS day, count(*) AS legacy_ai_mediated
            FROM analytics_mirror.requests
           WHERE visitor_type='ai_mediated'
             AND ts >= (now() AT TIME ZONE 'UTC')::date - 29
           GROUP BY 1
        ),
        proposed AS (
          SELECT (ts AT TIME ZONE 'UTC')::date AS day, count(*) AS new_ai_referred_human
            FROM analytics_mirror.requests
           WHERE is_bot = 0
             AND referrer_domain = ANY(%s)
             AND ts >= (now() AT TIME ZONE 'UTC')::date - 29
           GROUP BY 1
        ),
        bots AS (
          SELECT (ts AT TIME ZONE 'UTC')::date AS day, count(*) AS ai_bot_crawls
            FROM analytics_mirror.requests
           WHERE is_ai_bot = 1
             AND ts >= (now() AT TIME ZONE 'UTC')::date - 29
           GROUP BY 1
        )
        SELECT d.day,
               COALESCE(l.legacy_ai_mediated, 0)   AS legacy_ai_mediated,
               COALESCE(p.new_ai_referred_human,0) AS new_ai_referred_human,
               COALESCE(b.ai_bot_crawls,0)         AS ai_bot_crawls
          FROM days d
          LEFT JOIN legacy   l USING (day)
          LEFT JOIN proposed p USING (day)
          LEFT JOIN bots     b USING (day)
         ORDER BY d.day;
        """,
        (list(NEW_ENGINES),),
    )
    return cur.fetchall()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sources.analytics_mirror_cursor() as (_, cur):
        diag = diagnostics(cur)
        rows = daily_comparison(cur)

    with CSV_PATH.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "legacy_ai_mediated", "new_ai_referred_human", "ai_bot_crawls"])
        for d, legacy, new, bots in rows:
            w.writerow([d.isoformat(), legacy, new, bots])

    tot_legacy = sum(r[1] for r in rows)
    tot_new = sum(r[2] for r in rows)
    tot_bots = sum(r[3] for r in rows)
    overcount = round(tot_legacy / max(tot_new, 1), 1)

    summary = {
        "task": "FU-CONVERSION-20260424-11",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "totals_30d": {
            "legacy_ai_mediated": tot_legacy,
            "new_ai_referred_human": tot_new,
            "ai_bot_crawls": tot_bots,
            "legacy_over_new_ratio": overcount,
        },
        "diagnostics": diag,
        "outputs": {
            "csv": str(CSV_PATH),
            "proposal_doc": str(PROPOSAL_PATH),
        },
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
