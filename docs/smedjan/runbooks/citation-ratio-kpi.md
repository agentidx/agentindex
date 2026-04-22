# Citation-ratio North Star KPI

**Owner:** Smedjan factory · citation workstream
**Purpose:** Document the `analytics_mirror.citation_ratio_daily` view and
how it feeds the weekly Smedjan audit + Buzz reports. Promoted to North
Star KPI by **FU-CITATION-20260422-01** (AUDIT-CITATION-20260422
Finding 1, critical).

---

## Why a ratio, not a volume

Ingestion is saturated. Between 2026-04-18 and 2026-04-22 the 30-day
AI-bot crawl count grew from 5,253,834 → 5,349,252 (+1.8%) while
ai_mediated visits grew 36,428 → 36,683 (+0.7%). The ratio worsened from
144:1 to 146:1. Growing crawl volume without growing citation yield is
the bottleneck — headlining raw crawl volume hides that.

Finding 10 sharpened the split: 94.4% of AI-bot traffic is
`bot_purpose='training'`, 0.7% is `user_triggered`. `user_triggered`
crawls track ai_mediated visits **~1.02 : 1** — an excellent real-time
conversion signal that the 146:1 global headline dilutes. The view
therefore carries per-purpose rows plus an 'all' rollup so both numbers
are one `WHERE` clause away.

---

## View shape

```
 day         | bot_purpose    | crawls | ai_mediated | ratio
-------------+----------------+--------+-------------+--------
 2026-04-21  | all            | 131417 |        1256 | 104.63
 2026-04-21  | search_index   |   5648 |        1256 |   4.50
 2026-04-21  | training       | 124492 |        1256 |  99.12
 2026-04-21  | user_triggered |   1277 |        1256 |   1.02
```

- `day` — request `ts` truncated to UTC date.
- `bot_purpose` — one row per purpose present on that day, plus an
  `'all'` rollup summing every purpose (and any future values). Coalesces
  NULL purposes to `'(unknown)'`.
- `crawls` — count of `requests` rows with `is_ai_bot = 1` in the bucket.
- `ai_mediated` — count of `requests` rows with
  `visitor_type = 'ai_mediated'` **for that day** (same value on every
  per-purpose row because ai_mediated visits are human clicks, not bot
  hits, and have no bot_purpose attribution).
- `ratio` — `crawls / ai_mediated`, rounded to 2 decimals. `NULL` when
  no ai_mediated visits landed that day.

### Gotcha — do not sum `ai_mediated` across per-purpose rows

The daily ai_mediated value is duplicated across every purpose row so
that the ratio is self-contained per row. Summing `ai_mediated` across
purposes for the same day triple-counts. Always filter
`bot_purpose = 'all'` when aggregating the denominator.

---

## How to use it

### Global headline (weekly audit + Buzz report)

```sql
SELECT sum(crawls)       AS crawls_7d,
       sum(ai_mediated)  AS ai_mediated_7d,
       round(sum(crawls)::numeric / nullif(sum(ai_mediated), 0), 2)
                         AS ratio_7d
  FROM analytics_mirror.citation_ratio_daily
 WHERE bot_purpose = 'all'
   AND day >= current_date - 7;
```

### Week-over-week delta (the acceptance criterion)

```sql
SELECT bot_purpose,
       sum(crawls) FILTER (WHERE day >= current_date - 7)               AS crawls_7d,
       sum(ai_mediated) FILTER (WHERE day >= current_date - 7
                                 AND bot_purpose = 'all')               AS mediated_7d,
       sum(crawls) FILTER (WHERE day >= current_date - 14
                            AND day <  current_date - 7)                AS crawls_prev_7d,
       sum(ai_mediated) FILTER (WHERE day >= current_date - 14
                                 AND day <  current_date - 7
                                 AND bot_purpose = 'all')               AS mediated_prev_7d
  FROM analytics_mirror.citation_ratio_daily
 WHERE day >= current_date - 14
 GROUP BY 1 ORDER BY 1;
```

One query, one cursor round-trip. The `bot_purpose='all'` filter inside
the `ai_mediated` aggregate prevents the triple-count described above.

### user_triggered yield (the signal the global ratio hides)

```sql
SELECT day, crawls, ai_mediated, ratio
  FROM analytics_mirror.citation_ratio_daily
 WHERE bot_purpose = 'user_triggered'
   AND day >= current_date - 14
 ORDER BY day;
```

Expect `ratio` ≈ 1.0 ± 0.1. A spike above 2.0 for two consecutive days
means a human-triggered bot is crawling but the human isn't landing — a
redirect, rate-limit, or 4xx on the cited URL. Escalate to the citation
workstream the same week.

### The three required headline rows, in one query

Produces the exec-summary headlines mandated by the reporting contract
below (global ratio, user_triggered conversion, training_share). The
`N` bind variable is the audit window in days (7 for WoW, 30 for the
standard weekly exec summary).

```sql
WITH win AS (
    SELECT sum(crawls) AS crawls_window
      FROM analytics_mirror.citation_ratio_daily
     WHERE bot_purpose = 'all'
       AND day >= current_date - :N
),
mediated AS (
    SELECT sum(ai_mediated) AS mediated_window
      FROM analytics_mirror.citation_ratio_daily
     WHERE bot_purpose = 'all'
       AND day >= current_date - :N
),
by_purpose AS (
    SELECT bot_purpose, sum(crawls) AS crawls_window
      FROM analytics_mirror.citation_ratio_daily
     WHERE bot_purpose IN ('all','training','user_triggered','search_index')
       AND day >= current_date - :N
     GROUP BY bot_purpose
)
SELECT
    'ratio_all'          AS headline,
    (SELECT crawls_window FROM win)                                  AS numerator,
    (SELECT mediated_window FROM mediated)                           AS denominator,
    round((SELECT crawls_window FROM win)::numeric
          / nullif((SELECT mediated_window FROM mediated), 0), 2)    AS value
UNION ALL SELECT
    'ratio_user_triggered',
    bp.crawls_window,
    (SELECT mediated_window FROM mediated),
    round(bp.crawls_window::numeric
          / nullif((SELECT mediated_window FROM mediated), 0), 2)
  FROM by_purpose bp WHERE bp.bot_purpose = 'user_triggered'
UNION ALL SELECT
    'training_share',
    bp.crawls_window,
    (SELECT crawls_window FROM win),
    round(bp.crawls_window::numeric
          / nullif((SELECT crawls_window FROM win), 0), 4)
  FROM by_purpose bp WHERE bp.bot_purpose = 'training';
```

Three rows out, one cursor round-trip. `value` is a ratio for the first
two headlines and a share (0–1) for `training_share`.

---

## Apply / refresh

The view is idempotent — `CREATE OR REPLACE VIEW` — and defined in
`~/agentindex/smedjan/measurement/citation_ratio_daily.sql`.

```bash
set -a; . ~/smedjan/config/.env; set +a
PGPASSWORD=$SMEDJAN_APP_PW \
    /opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
        -h smedjan -U smedjan_app -d smedjan \
        -f ~/agentindex/smedjan/measurement/citation_ratio_daily.sql
```

No refresh job is needed — the view aggregates live from
`analytics_mirror.requests`, which is rebuilt nightly from Mac Studio by
`scripts/smedjan-analytics-export.sh` + the import counterpart on the
smedjan host. Mirror freshness is bounded by that pipeline; check with
`smedjan.sources.mirror_freshness_hours()` before quoting a ratio if it
matters (M13 alerts when > 48h).

Retention: `requests` is a 30-day rolling window. The view therefore
only carries ~30 distinct `day` values at any time. Plan longer horizons
by snapshotting to a smedjan table if the 30-day limit bites.

---

## Reporting contract

Smedjan weekly audit (`smedjan.audit_scheduler` → `citation`) must
headline the crawl-to-cited ratio in the executive summary, **not** raw
crawl volume. The scheduler's `citation.focus` string enforces the
contract for the worker prompt.

Buzz's weekly report (in `~/.openclaw/workspace/OPERATIONSPLAN.md` and
the Discord digest) should quote the same numbers. Changes to Buzz's
behaviour are out of scope for this task — the view exists and is
queryable today; Buzz's next operator pass can point it at the view
instead of its current raw-volume query.

### What "headline" means in the executive summary

The Exec-Summary table must carry at least these three headline rows,
in order, each alongside the prior audit's value and the delta:

1. **Crawl-to-cited ratio (all)** — `bot_purpose='all'` over the audit
   window. The North Star KPI.
2. **user_triggered conversion ratio** — `bot_purpose='user_triggered'`.
   The real-time citation yield; expected ≈ 1.0 ± 0.1. This is the
   signal the global ratio hides — user_triggered crawls track
   ai_mediated visits nearly 1:1, while training traffic dilutes the
   global headline by ~100×.
3. **training_share** — training crawls ÷ all crawls over the window.
   A dilution / volume proxy. Expect ≈ 94%; material shifts here mean
   the composition of bot traffic changed, not the citation surface.

`search_index` may be surfaced as a supporting row below the three
required headlines. Raw 30-day AI-bot crawl volume may still appear,
but **below** the ratios, not above them.

### Prior-audit KPI baseline (the "last audit" column for 2026-04-29)

From AUDIT-CITATION-20260422 (30-day window 2026-03-23 → 2026-04-22):

| Headline | 2026-04-22 value |
|---|---:|
| Crawl-to-cited ratio (all) | **146 : 1** (5,349,252 ÷ 36,683) |
| user_triggered conversion ratio | **1.02 : 1** (37,513 ÷ 36,683) |
| training_share | **94.4%** (5,047,063 ÷ 5,349,252) |
| search_index share (supporting) | 4.9% (264,628 ÷ 5,349,252) |
| user_triggered share (supporting) | 0.7% (37,513 ÷ 5,349,252) |

Next week's audit should populate the `Δ` column against these numbers.
AUDIT-CITATION-20260422 Finding 10 established this split; future
audits inherit it via the scheduler focus and this runbook.

---

*Last updated: 2026-04-22 (FU-CITATION-20260422-10 prescribed the
three-headline contract and recorded the bot_purpose baseline; the
view itself was landed by FU-CITATION-20260422-01).*
