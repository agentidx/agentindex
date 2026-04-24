"""FU-CONVERSION-20260424-10 — Split ai_crawler vs ai_referrer in analytics ingest.

Parent: AUDIT-CONVERSION-20260424 · Finding 10.

Read-only audit script that regenerates the row-count evidence backing
the proposal at:

    /Users/anstudio/smedjan/audit-reports/2026-04-24-FU-CONVERSION-20260424-10-ai-crawler-vs-referrer-proposal.md

No schema changes, no writes — this script only classifies one sample
day and one 30-day window under both the old (`ai_source`) and the
proposed (`ai_crawler` / `ai_referrer`) definitions and drops the CSV
the proposal cites.

The split follows the same lookup tables already in
`agentindex/analytics.py::classify_ai_source`:

    ai_crawler  ← user-agent fragments in _AI_MEDIATED_UA_FRAGMENTS
                  (chatgpt-user, claude-user, perplexity-user)
    ai_referrer ← referrer_domain in _AI_REFERRER_DOMAINS (9 domains)
                  plus the two _AI_CONDITIONAL_DOMAINS
                  (bing.com/chat, x.com/i/grok) and the duckduckgo /
                  brave summariser conditionals.

Usage::

    PYTHONPATH=/Users/anstudio/agentindex-factory \\
        /Users/anstudio/agentindex/venv/bin/python3 \\
        /Users/anstudio/agentindex/smedjan/audits/FU-CONVERSION-20260424-10.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

from smedjan import sources

OUT_DIR = Path("/Users/anstudio/smedjan/audit-reports")
CSV_PATH = OUT_DIR / "2026-04-24-FU-CONVERSION-20260424-10-daily-reclassification.csv"
EVIDENCE_PATH = OUT_DIR / "2026-04-24-FU-CONVERSION-20260424-10-evidence.json"
PROPOSAL_PATH = OUT_DIR / "2026-04-24-FU-CONVERSION-20260424-10-ai-crawler-vs-referrer-proposal.md"

SAMPLE_DAY = "2026-04-23"

# SQL fragments that mirror the Python classifier in analytics.py exactly.
AI_CRAWLER_CASE = """
    CASE
      WHEN LOWER(COALESCE(user_agent,'')) LIKE '%%chatgpt-user%%'    THEN 'ChatGPT'
      WHEN LOWER(COALESCE(user_agent,'')) LIKE '%%claude-user%%'     THEN 'Claude'
      WHEN LOWER(COALESCE(user_agent,'')) LIKE '%%perplexity-user%%' THEN 'Perplexity'
    END
"""

AI_REFERRER_CASE = """
    CASE
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'claude.ai'               THEN 'Claude'
      WHEN LOWER(COALESCE(referrer_domain,'')) IN ('chat.openai.com','chatgpt.com') THEN 'ChatGPT'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'perplexity.ai'           THEN 'Perplexity'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'copilot.microsoft.com'   THEN 'Copilot'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'gemini.google.com'       THEN 'Gemini'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'grok.x.ai'               THEN 'Grok'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'kagi.com'                THEN 'Kagi'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'doubao.com'              THEN 'Doubao'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'bing.com'
           AND LOWER(COALESCE(referrer,'')) LIKE '%%/chat%%'               THEN 'Copilot'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'x.com'
           AND LOWER(COALESCE(referrer,'')) LIKE '%%/i/grok%%'             THEN 'Grok'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'duckduckgo.com'
           AND (LOWER(COALESCE(referrer,'')) LIKE '%%ia=%%'
                OR LOWER(COALESCE(referrer,'')) LIKE '%%ai=%%')            THEN 'DuckDuckGo AI'
      WHEN LOWER(COALESCE(referrer_domain,'')) = 'search.brave.com'
           AND LOWER(COALESCE(referrer,'')) LIKE '%%summarizer%%'          THEN 'Brave AI'
    END
"""


def _recount(cur, where_ts: str, params: tuple) -> dict:
    cur.execute(
        f"""
        WITH tagged AS (
            SELECT is_bot, ai_source,
                   {AI_CRAWLER_CASE}  AS ai_crawler,
                   {AI_REFERRER_CASE} AS ai_referrer
              FROM analytics_mirror.requests
             WHERE {where_ts}
               AND status < 400 AND method = 'GET'
        )
        SELECT
          SUM(CASE WHEN ai_source   IS NOT NULL                     THEN 1 ELSE 0 END) AS old_total,
          SUM(CASE WHEN ai_source   IS NOT NULL AND is_bot = 0      THEN 1 ELSE 0 END) AS old_human,
          SUM(CASE WHEN ai_source   IS NOT NULL AND is_bot = 1      THEN 1 ELSE 0 END) AS old_bot,
          SUM(CASE WHEN ai_crawler  IS NOT NULL                     THEN 1 ELSE 0 END) AS crawler_total,
          SUM(CASE WHEN ai_crawler  IS NOT NULL AND is_bot = 0      THEN 1 ELSE 0 END) AS crawler_humanflag,
          SUM(CASE WHEN ai_crawler  IS NOT NULL AND is_bot = 1      THEN 1 ELSE 0 END) AS crawler_bot,
          SUM(CASE WHEN ai_referrer IS NOT NULL                     THEN 1 ELSE 0 END) AS referrer_total,
          SUM(CASE WHEN ai_referrer IS NOT NULL AND is_bot = 0      THEN 1 ELSE 0 END) AS referrer_human,
          SUM(CASE WHEN ai_referrer IS NOT NULL AND is_bot = 1      THEN 1 ELSE 0 END) AS referrer_bot,
          SUM(CASE WHEN ai_crawler  IS NOT NULL AND ai_referrer IS NOT NULL THEN 1 ELSE 0 END) AS both,
          COUNT(*) AS total_rows
          FROM tagged;
        """,
        params,
    )
    row = cur.fetchone()
    cols = [d.name for d in cur.description]
    return dict(zip(cols, row))


def main() -> int:
    evidence: dict = {"sample_day": SAMPLE_DAY, "generated_at": dt.datetime.utcnow().isoformat()}

    with sources.analytics_mirror_cursor() as (_, cur):
        evidence["sample_day_counts"] = _recount(
            cur,
            "ts >= %s::date AND ts < (%s::date + INTERVAL '1 day')",
            (SAMPLE_DAY, SAMPLE_DAY),
        )
        evidence["thirty_day_counts"] = _recount(
            cur,
            "ts >= now() - INTERVAL '30 days'",
            (),
        )

        # Per-day CSV for the 30d window — lets us spot sparse ai_referrer days.
        cur.execute(
            f"""
            SELECT (ts AT TIME ZONE 'UTC')::date AS day,
                   SUM(CASE WHEN ai_source IS NOT NULL THEN 1 ELSE 0 END) AS old_ai_source,
                   SUM(CASE WHEN ai_source IS NOT NULL AND is_bot=0 THEN 1 ELSE 0 END) AS old_ai_source_human,
                   SUM(CASE WHEN ({AI_CRAWLER_CASE}) IS NOT NULL THEN 1 ELSE 0 END) AS new_ai_crawler,
                   SUM(CASE WHEN ({AI_REFERRER_CASE}) IS NOT NULL THEN 1 ELSE 0 END) AS new_ai_referrer,
                   SUM(CASE WHEN ({AI_REFERRER_CASE}) IS NOT NULL AND is_bot=0 THEN 1 ELSE 0 END) AS new_ai_referrer_human
              FROM analytics_mirror.requests
             WHERE ts >= now() - INTERVAL '30 days'
               AND status < 400 AND method = 'GET'
             GROUP BY 1 ORDER BY 1;
            """
        )
        daily_rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        with CSV_PATH.open("w") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in daily_rows:
                w.writerow(r)
        evidence["daily_csv"] = str(CSV_PATH)
        evidence["daily_csv_rows"] = len(daily_rows)

    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, default=str))
    print(f"wrote  {CSV_PATH} ({evidence['daily_csv_rows']} daily rows)")
    print(f"wrote  {EVIDENCE_PATH}")
    print(f"proposal: {PROPOSAL_PATH}")
    print()
    print("Sample day 2026-04-23:")
    for k, v in evidence["sample_day_counts"].items():
        print(f"  {k:20s} = {v}")
    print("\n30-day window:")
    for k, v in evidence["thirty_day_counts"].items():
        print(f"  {k:20s} = {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
