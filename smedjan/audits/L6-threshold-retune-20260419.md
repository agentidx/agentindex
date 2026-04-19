# L6 Canary Threshold Retune — 2026-04-19

> **Status: PROPOSAL — requires Anders approval before any value lands in
> `scripts/canary_monitor_l1.py`.** This task (T164) explicitly forbids
> auto-application.

## Method

30 days of `analytics_mirror.*` history were pulled from the Smedjan
Postgres replica (window `2026-03-20T08:00Z → 2026-04-19T08:00Z`). Each
canary condition was reconstructed against the same surface the runtime
monitor evaluates:

| condition               | reconstruction source                                                   | native granularity   |
|-------------------------|-------------------------------------------------------------------------|----------------------|
| canary 5xx (gems+brew)  | `analytics_mirror.requests` ⨝ `software_registry` slug set (Nerq RO)    | per 30-min bucket    |
| whole-site 5xx pct      | `analytics_mirror.requests_daily` (full copy, unfiltered)               | per day              |
| write rate (req/min)    | `analytics_mirror.requests_daily` total → daily mean req/min            | per day (see caveat) |
| citation rate (NEW)     | `analytics_mirror.requests` filtered on `is_ai_bot=1` + `/safe/%`        | per hour             |

**Canary cohort** — 18,021 non-King, enriched gems + homebrew slugs
materialised from Nerq RO into a session-local `TEMP TABLE` and joined
against `/safe/<slug>/…` on the mirror.

**Write-rate caveat** — the mirror's `requests` table is filtered (AI
bots + /safe/compare/best/alternatives + status≥400), so 5-min rolling
granularity cannot be reconstructed from it. The proposal scales the
existing runtime threshold by the observed daily-mean drift instead of
direct per-5-min fit, and recommends a follow-up measurement task to
capture 5-min granularity at source (see §5).

## 1. Canary 5xx (gems + homebrew `/safe/*`, 30-min window)

**Current threshold:** page when `5xx ≥ 3` in the last 30 min.
**Observed (30d):** 1,376 buckets, 35,913 cohort requests, **183 5xx
events**.

```
p50  = 0.00    p95  = 0.00    p99  = 4.00
p90  = 0.00    p99.9 = 7.00   max  = 9.00
```

ASCII-histogram of per-30-min 5xx counts (bin 0 = zero events, which
dominates):

```
  0.0 – 0.9 |██████████████████████████████████████████████████ 1309
  0.9 – 1.8 |                                                     25
  1.8 – 2.7 |                                                     12
  2.7 – 3.6 |                                                      9
  3.6 – 4.5 |                                                     10
  4.5 – 5.4 |                                                      6
  5.4 – 6.3 |                                                      0
  6.3 – 7.2 |                                                      4
  7.2 – 8.1 |                                                      0
  8.1 – 9.0 |                                                      1
```

**Rationale** — 19 of 1,376 buckets (≈1.4 %) already breach the current
floor of 3 during normal operation. That is louder than the "rare
transient" design intent (0/2,318 baseline cited in the runtime
docstring). The right anchor is the tail above routine noise.
**p99.9 = 7** events in a 30-min window is the highest regularly-seen
level; anything above that is meaningful.

**Recommendation: `CANARY_5XX_FLOOR_30M = 8` (current 3)**

- Fires when observed 5xx exceeds the empirical p99.9 by ≥ 1 event.
- Would have paged 1 of the last 1,376 buckets (the lone max=9 event)
  versus ~19 pages under the current rule over the same period.
- Leaves 3 open as a tighter cohort-level debug threshold if a future
  higher-severity registry (e.g. `crypto`) is canary-rotated.

## 2. Whole-Nerq 5xx percentage (30-min window)

**Current threshold:** page when 5xx rate > 0.2 % over 30 min.
**Observed (30d, daily granularity):** 21,000,558 requests, **3,991 5xx
events**, aggregate 0.01900 %.

```
p50  = 0.00053%   p95  = 0.11089%   p99  = 0.24313%
p90  = 0.04068%                     max  = 0.29675%
```

Daily 5xx-pct distribution:

```
  0.00000% – 0.02967% |██████████████████████████████████████████████████ 26
  0.02967% – 0.05935% |█                                                   1
  0.05935% – 0.08902% |                                                    0
  0.08902% – 0.11870% |███                                                 2
  0.11870% – 0.14837% |                                                    0
  0.14837% – 0.17805% |                                                    0
  0.17805% – 0.20772% |                                                    0
  0.20772% – 0.23740% |                                                    0
  0.23740% – 0.26707% |                                                    0
  0.26707% – 0.29675% |█                                                   1
```

**Rationale** — 1 of 30 days (the 2026-04-… spike at 0.297 %) already
pierces the current 0.2 % floor, and p99 sits at 0.243 %, i.e. benign
days land within the same decade as the alert threshold. The current
value would have paged on ~3 % of days without a real incident. Move
the threshold above the observed p99 while staying well below anything
that the monthly 3,991 5xx baseline implies is a genuine outage.

**Recommendation: `WHOLE_5XX_PCT_30M = 0.5` % (current 0.2)**

- ≈ 2.1 × observed 30-day maximum, ≈ 26 × aggregate 30d rate.
- Retains the runtime docstring's original spirit ("~800 × baseline").
  New aggregate baseline is 0.019 %; 0.5 % is ~26 × baseline — still a
  clear alarm signal, but outside normal daily noise.
- **Secondary safeguard (optional):** add a *minimum absolute count of
  ≥ 50 5xx in the window* so a 30-min bucket with 500 total requests
  and 3 errors (0.6 %) does not page. Tracked as follow-up §5.

## 3. Write rate (req/min over 5-min window)

**Current threshold:** page when 5m rolling write rate < 150 req/min.
**Observed (30d daily means, proxy for 5-min p01 — see caveat above):**

```
p01  = 119.8    p25  = 310.0    p75  = 622.0    p99  = 860.0
p05  = 174.3    p50  = 500.6    p90  = 787.5
```

Daily mean req/min histogram:

```
    114.6 –   190.3 |████████████████                                    2
    190.3 –   266.0 |█████████████████████████                           3
    266.0 –   341.7 |██████████████████████████████████████████████████  6
    341.7 –   417.4 |                                                    0
    417.4 –   493.1 |█████████████████████████                           3
    493.1 –   568.8 |█████████████████████████████████████████           5
    568.8 –   644.6 |█████████████████████████████████                   4
    644.6 –   720.3 |████████████████                                    2
    720.3 –   796.0 |████████████████                                    2
    796.0 –   871.7 |█████████████████████████                           3
```

**Rationale** — the runtime docstring calibrated against a 7-day
`p50_5min ≈ 736 req/min` baseline and picked 150 (≈ 20 % of p50, just
below `p01_5min ≈ 188`). The 30d daily-mean p50 is now **500 req/min**,
a ~32 % drop relative to the original baseline (consistent with the
write-rate investigation filed 2026-04-18, see
`~/smedjan/observations/write-rate-investigation-20260418.md`).

Two options:

- **Preserve ratio (recommended):** scale threshold by the same 0.68 ×
  the baseline shifted and round down to a clean value.
  `150 × 500/736 ≈ 102` → **100 req/min**.
- **Preserve absolute floor:** keep 150 req/min. Risk: current daily
  means land in the 115–175 range ~5 % of days, and 5-min windows
  have a fatter left tail than the daily mean, so false positives
  likely already increased.

**Recommendation: `WRITE_RATE_MIN_PER_MIN_5M = 100` (current 150)**

- Preserves the `threshold ≈ 20 % of current p50` relationship the
  original calibration targeted.
- 5-min granularity not reconstructible from mirror; §5 proposes a
  one-shot measurement task on Mac Studio (`analytics.db` is local)
  to confirm `p01_5min` before shipping this change.

## 4. Citation rate (NEW — AI-bot `/safe/*` hits/hr, 3-hour streak)

**Status:** no runtime condition today — proposing addition.

**Observed (30d, 703 hourly buckets):** 157,641 AI-bot `/safe/*` hits.

```
p01 =  6        p25 =  82.5     p75 = 243       p99 = 1183.8
p05 = 27        p50 = 146       p90 = 541.2
p10 = 48
```

Hourly AI-bot `/safe/*` hits histogram:

```
      3 –  181 |██████████████████████████████████████████████████ 425
    181 –  359 |█████████████████                                  151
    359 –  537 |██████                                              56
    537 –  715 |████                                                39
    715 –  894 |█                                                   11
    894 – 1072 |█                                                   12
   1072 – 1250 |                                                     2
   1250 – 1428 |                                                     2
   1428 – 1606 |                                                     1
   1606 – 1784 |                                                     4
```

**Why add it?** AI citations are the top-of-funnel Smedjan is optimising
for (see `docs/strategy/nerq-ai-citation-optimization-sprint.md`). A
bot-blocklist, tunnel misroute, or robots.txt regression would drop
citations to zero before 5xx rates move. Per CLAUDE.md "welcome all
traffic" we explicitly want to page on sudden AI-crawler silence.

**Rationale for threshold** — hourly citation traffic is noisy: hours
under p05=27 exist routinely (single-hour dips across timezones).
Firing on a single hour would be too loud. Require **3 consecutive
hours** below the floor to declare the cohort silenced. 20 is chosen
(below p05=27) so that organic quiet hours never trip 3-in-a-row unless
citations truly stop.

**Recommendation (NEW): `CITATION_RATE_MIN_PER_HOUR_3H_STREAK = 20`**

- Condition: `citation_rate_hourly < 20` for 3 consecutive full hours
  in the mirror's AI-bot `/safe/*` stream.
- In the observed 30d, no 3-hour streak at or below 20 occurred.
- State/dedup: reuse the canary-monitor `state_file` scheme; dedup
  window 2 h (citation outages need faster re-page if unresolved).

## 5. Summary & follow-ups

| Condition     | Current            | Proposed            | Delta |
|---------------|--------------------|---------------------|-------|
| canary 5xx    | `≥ 3` / 30 min     | `≥ 8` / 30 min      | +5    |
| whole 5xx pct | `> 0.2 %` / 30 min | `> 0.5 %` / 30 min  | +0.3pp|
| write rate    | `< 150` / 5 min    | `< 100` / 5 min     | –50   |
| citation rate | (none)             | `< 20/hr × 3h`      | NEW   |

**Needs Anders approval** — this is a proposal document only. No file in
`scripts/canary_monitor_l1.py` is modified by this task.

**Recommended follow-up tasks** (create via `scripts/smedjan queue add`):

- **T164-F1 (L6 / low risk)** — measure true 5-min write-rate
  distribution on Mac Studio `~/agentindex/logs/analytics.db` (where
  the data is unfiltered). Confirm p01/p05/p10 before shipping the
  write-rate change.
- **T164-F2 (L6 / low risk)** — add optional "absolute count ≥ 50"
  guard on the whole-site 5xx pct condition so quiet-traffic half-hours
  cannot page via a tiny denominator.
- **T164-F3 (L6 / low risk)** — wire the citation-rate condition into
  `canary_monitor_l1.py` only after Anders signs off on this proposal.

## Appendix — reproduction

Run the analysis end-to-end (no write paths):

```
set -a; source ~/smedjan/config/.env; set +a
PYTHONPATH=~/agentindex ~/agentindex/venv/bin/python3 /tmp/l6_threshold_retune.py
```

Source query shapes are in `/tmp/l6_threshold_retune.py` (retained for
this retune only; not committed — all logic is printed inline in §§1–4
for audit).
