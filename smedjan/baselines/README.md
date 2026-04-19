# ai_mediated daily baseline — 2026-04-18 snapshot

This directory holds the formal **lift denominators** for the F-series conversion
follow-ups from `AUDIT-CONVERSION-20260418`. `ai_mediated_daily_2026-04-18.csv`
is the 30-day pre-intervention baseline of daily AI-referred human sessions
(`visitor_type = 'ai_mediated'`) against which all F-series surface changes are
measured.

## Why this exists

Finding 11 of the 2026-04-18 conversion audit (severity: medium) established that
daily `ai_mediated` volume is flat at ~1,100/day across 30 days while AI-bot
ingestion is climbing from ~280K to 300K+/day. Ingestion is growing; reader
landings are not. Every F-series follow-up that claims to "lift conversion" must
measure lift *against this flatline*, not against an unconditional before/after —
otherwise a rising tide (which does not exist here) would flatter the numbers.

Every F-series follow-up listed below uses this file as denominator.

## What's in the CSV

- `day` — ISO date (UTC day-bucket via `date_trunc('day', ts)`).
- `ai_mediated_count` — COUNT of rows in `analytics_mirror.requests` with
  `visitor_type = 'ai_mediated'` for that day.

Window: 2026-03-20 .. 2026-04-18 (30 rows, inclusive of both edges).

The 2026-03-20 row (429) and the 2026-04-18 row (540) are the **partial-day
edges** of the 30-day rolling window at snapshot time (2026-04-19 ~11:00 UTC).
Drop both before computing a clean denominator.

Summary (full 30 rows):
- mean: 1213.5/day
- mean over 28 clean-interior days: 1265.6/day
- max: 1655 (2026-03-23)
- min interior: 1030 (2026-04-04)

## How to recompute (weekly cadence)

Run this exact query against `analytics_mirror.requests` on the Smedjan DB.
The snapshot date in the filename should be the wall-clock date the recompute is
run on; the window is always the trailing 30 days.

```sql
SELECT date_trunc('day', ts)::date AS day,
       count(*) FILTER (WHERE visitor_type='ai_mediated') AS ai_mediated_count
  FROM analytics_mirror.requests
 WHERE ts >= now() - interval '30 days'
 GROUP BY 1
 ORDER BY 1;
```

Python one-liner (preferred — uses the `smedjan.sources` abstraction):

```bash
PYTHONPATH=/Users/anstudio/agentindex /Users/anstudio/agentindex/venv/bin/python3 - <<'PY'
import csv, sys, datetime as dt
from smedjan import sources
with sources.analytics_mirror_cursor() as (_, cur):
    cur.execute("""
        SELECT date_trunc('day', ts)::date AS day,
               count(*) FILTER (WHERE visitor_type='ai_mediated') AS ai_mediated_count
          FROM analytics_mirror.requests
         WHERE ts >= now() - interval '30 days'
         GROUP BY 1 ORDER BY 1
    """)
    rows = cur.fetchall()
snap = dt.date.today().isoformat()
out = f"/Users/anstudio/agentindex/smedjan/baselines/ai_mediated_daily_{snap}.csv"
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["day", "ai_mediated_count"])
    w.writerows(rows)
print(f"wrote {out} ({len(rows)} rows)")
PY
```

**Cadence:** every Saturday morning (after the analytics_mirror sync). Keep all
historical snapshots in this directory — never overwrite. The most recent file
is the active denominator; older files let us re-run an F-series lift analysis
against the denominator that was valid at the time the intervention shipped.

## Referenced by

The following F-series follow-ups from `AUDIT-CONVERSION-20260418` measure their
14-day lift against this baseline (and so should cite the snapshot filename that
was active on their ship date):

- `FU-CONVERSION-20260418-01` — F01: ZARQ trust-score block on top-5 AI-landing surfaces.
- `FU-CONVERSION-20260418-03` — F03: Attribution / referrer capture (denominator used for "attributed share of ai_mediated").
- `FU-CONVERSION-20260418-06` — F06: Homepage hero tuned for AI-reader intent.
- `FU-CONVERSION-20260418-07` — F07: Trust-verdict + capture widget on `/dataset/*`.
- `FU-CONVERSION-20260418-10` — F10: AI-cohort-first rollout rule for conversion experiments.

Evidence signal broadcast on snapshot date: `baseline_ai_mediated_daily_2026-04-18`
(see `smedjan queue evidence list`).

## Provenance

- Source table: `analytics_mirror.requests` (mirror of Nerq `agentindex.analytics.requests`).
- Snapshot taken: 2026-04-19 ~11:00 UTC (via `smedjan.sources.analytics_mirror_cursor()`).
- Audit this baseline belongs to: `smedjan/audit-reports/2026-04-18-conversion.md`, Finding 11.
- Task: `FU-CONVERSION-20260418-11`.
