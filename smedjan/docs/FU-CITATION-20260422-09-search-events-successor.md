# FU-CITATION-20260422-09 — `search_events` provenance & search_query decision

*Filed: 2026-04-22 · linked to `AUDIT-CITATION-20260422` finding #9.*

## TL;DR

`analytics_mirror.search_events` IS the intended successor to
`requests.search_query` for "top user-search queries" intent signal.
**search_query should be deprecated** for that purpose (it is and always
was a best-effort middleware side-channel, not a first-class event log).
The successor writer exists on branch `smedjan-factory-v0` but is **not
currently deployed to Nerq-prod**, which is why the mirror shows only
6 rows — all captured during a ~17-hour window on 2026-04-19/20 when a
test build of the factory branch was briefly live. The writer must be
merged to `main` and redeployed before the weekly audit on 2026-04-29 or
the same blind spot repeats.

## Provenance

### `search_events` (new, intended successor)

| Layer | Path | Source |
|---|---|---|
| Schema (Nerq SQLite) | `logs/analytics.db` → `search_events` | `agentindex/api/search_events.py` `_SCHEMA` |
| Writer | `log_search_event()` | same module, called from `agentindex/api/discovery.py` `@app.get("/search")` |
| Export | nightly CSV | `scripts/smedjan-analytics-export.sh` `dump search_events` (full 30-day window, unfiltered) |
| Import | `analytics_mirror.search_events` | `~/smedjan/scripts/analytics-mirror-import.sh` |
| Schema (mirror) | `analytics_mirror.search_events` | `smedjan/schema_analytics_mirror.sql` |

Commit trail:

* `cfe675a` (2026-04-19 11:15 CEST) — "smedjan FU-QUERY-20260418-08:
  instrument `/search` into `analytics_mirror.search_events`". Lives on
  `smedjan-factory-v0`, **never merged to `main`**.
* Mirror rows: 6 total, `ts` range `2026-04-19 15:51Z → 2026-04-20 08:52Z`.
  All are bot probes (AwarioBot ×5, DotBot ×1). No further rows since
  2026-04-20 08:52Z. SQLite source (`logs/analytics.db`) confirms the
  same: `count=6, max(ts)=2026-04-20T08:52:02`. The writer has been dark
  for ~2 days.

Why dark: Nerq-prod runs from the primary worktree
`/Users/anstudio/agentindex` (branch `main`). `agentindex/api/search_events.py`
does not exist on `main`; `discovery.py` on `main` does not import
`log_search_event`. The 6 captured events date from a short-lived deploy
where the factory branch's `discovery.py` was in the main worktree —
that was reverted around 2026-04-20 08:52Z and no writer has run since.

### `search_query` (old, best-effort middleware hook)

| Layer | Path | Source |
|---|---|---|
| Writer | `AnalyticsMiddleware` | `agentindex/analytics.py:344` `log_request(…, search_query=…)`; pulled via `_extract_search_query(path, body)` for `/discover`, `/search`, and a handful of JSON search endpoints |
| Storage | `requests.search_query` column | `logs/analytics.db` (Nerq SQLite), one row per HTTP request |

Mirror volume is tiny (7 rows in 30 days) but the **Nerq SQLite source**
actually captures this — 1,248 non-empty `search_query` rows in the last
30 days (mostly `/discover?q=…`). The truncation is at the
export stage: `scripts/smedjan-analytics-export.sh` filters
`requests` to `is_ai_bot = 1 OR /safe% OR /compare% OR /best% OR
/alternatives% OR /search% OR status >= 400`. Human `/discover?q=`
searches (the overwhelming majority of that 1,248) do not match any of
those predicates and are dropped before rsync. The mirror's `7 / 7.4M`
headline is a filter artefact, not a writer regression.

Either way, `requests.search_query` is a poor shape for this job:
no `result_count`, no `duration_ms`, no dedicated zero-result index,
no `q_normalized` for aggregation, and it is entangled with the
per-request event log (20 GB and growing). `search_events` exists
precisely to give intent signal its own narrow, cheap, indexed table.

## Decision

1. **`search_events` is the intended successor.** Accelerate rollout.
2. **Deprecate `requests.search_query` for intent analysis** (weekly
   citation/query audits). Keep the column itself — ripping it out is
   not worth the analytics-middleware churn — but the 2026-04-29 audit
   and beyond should read from `analytics_mirror.search_events`, not
   from `requests.search_query`. Once volume is healthy, stop reporting
   the `search_query / total_requests` ratio at all; it is not
   informative.
3. **Follow-up required to deploy the writer to `main`** (this task is
   advisory — Nerq-prod deploys are explicit-authority only). The
   follow-up should merge cfe675a (or a clean cherry-pick of the
   `/search` hook + `search_events.py` module + export dump block) into
   `main`, verify `launchctl kickstart` picks it up, then tail
   `logs/analytics.db` until real human rows appear.

## Daily volume alert

`smedjan/scripts/check_search_events_volume.py` queries
`analytics_mirror.search_events` for the last 24 hours and warns if the
count is below the configured floor (default 50). The check is dormant
until 2026-04-26 (grace window for writer rollout) then active: before
that date the script exits 0 with a "dormant" line so it can safely sit
in cron.

Exit codes:

* `0` — healthy, dormant, or mirror unavailable (do not page for
  infra-level noise);
* `1` — below floor and past the grace date (actionable for the
  weekly auditor / factory operator).

Suggested invocation (cron or by-hand):

```
python3 -m smedjan.scripts.check_search_events_volume --floor 50
```

The script prints a one-line status suitable for the factory worker log
and does NOT call ntfy — this is an advisory check, not a human-page
condition. If the weekly auditor wants it elevated later, wire it into
`health_dashboard.py` or the weekly audit header.

## Acceptance-criteria map

| Criterion | Where |
|---|---|
| Note documenting `search_events` provenance + intended role | this file |
| Daily volume alert (warn if <50/day after 2026-04-26) | `smedjan/scripts/check_search_events_volume.py` |
| `search_query` keep/deprecate decision | §Decision item 2 above: **deprecate for intent analysis, column stays** |
