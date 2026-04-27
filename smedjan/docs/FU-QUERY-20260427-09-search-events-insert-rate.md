# FU-QUERY-20260427-09 — `search_events` synthetic-test wiring + insert-rate healthcheck

*Filed: 2026-04-27 · linked to `AUDIT-QUERY-20260427` finding #9 · supersedes still-blocked `FU-QUERY-20260420-11`.*

## TL;DR

* **Synthetic test confirms wiring is dark in production.** A
  `curl https://nerq.ai/search?q=smedjan-FU-QUERY-20260427-09-…` hit
  with a realistic Safari/macOS UA returned `HTTP 200` and rendered
  the results page, but produced **no row** in either `logs/analytics.db`
  `search_events` or `analytics_mirror.search_events`. Both stayed
  pinned at 6 rows / `max(ts)=2026-04-20 08:52:02Z` — the last brief
  factory-branch test deploy.
* **Root cause: the `/search` writer is committed to
  `smedjan-factory-v0` (commit `cfe675a`) but not merged to `main`;
  Nerq-prod runs from `main`, so `log_search_event()` is never called.**
  Diagnosed in detail in `FU-CITATION-20260422-09`; nothing has changed
  since.
* **Source-side healthcheck added.**
  `smedjan/scripts/check_search_events_insert_rate.py` watches the SQLite
  source (not the mirror — the mirror lags ≤24h), exits 1 when there
  are zero inserts in the last 24h, and can page via
  `ntfy_action_required INFRA_CRITICAL` with `--ntfy`. Active starting
  today (`--active-from 2026-04-27`).
* **Deploy of `cfe675a` to `main` is the only thing that closes this
  finding's first acceptance criterion (mirror row appears).** That step
  is held — Nerq-prod deploys are explicit-authority only and this task
  does not have that authority. STATUS: `needs_approval`.

## Synthetic-test evidence

```
$ curl -s -o /tmp/search_probe.html \
    -w "HTTP %{http_code} bytes=%{size_download} time=%{time_total}s\n" \
    -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15
        (KHTML, like Gecko) Version/17.5 Safari/605.1.15" \
    "https://nerq.ai/search?q=smedjan-FU-QUERY-20260427-09-1777309377"
HTTP 200 bytes=11482 time=1.960776s
```

Pre/post snapshots (sqlite + mirror, both probed within 10s of the curl):

| source | rows before | rows after | max(ts) before | max(ts) after |
|---|---|---|---|---|
| `logs/analytics.db` `search_events` (Mac Studio SQLite) | 6 | 6 | `2026-04-20T08:52:02` | unchanged |
| `analytics_mirror.search_events` (smedjan PG) | 6 | 6 | `2026-04-20 08:52:02+00` | unchanged |

The 6 retained rows are the AwarioBot×5 + DotBot×1 set captured during
the 17h factory-branch deploy on 2026-04-19/20 (see
`FU-CITATION-20260422-09` §Provenance for full commit trail).

Static evidence the writer is undeployed:

```
$ grep -n "log_search_event\|search_events" \
       /Users/anstudio/agentindex/agentindex/api/discovery.py
(no matches)

$ ls /Users/anstudio/agentindex/agentindex/api/search_events.py
ls: ...: No such file or directory

$ git branch --contains cfe675a
+ smedjan-factory-v0
```

The factory worktree at `/Users/anstudio/agentindex-factory` (branch
`smedjan-factory-v0`) has both the writer module and the
`discovery.py` call site, but the LaunchAgent
(`com.nerq.api`, `~/Library/LaunchAgents/com.nerq.api.plist`)
runs `/Users/anstudio/agentindex/venv/bin/python` against the `main`
worktree's `agentindex.api.discovery:app`, which lacks the wiring.

## Insert-rate healthcheck

`smedjan/scripts/check_search_events_insert_rate.py` adds a
source-side daily-zero detector to complement the existing
`check_search_events_volume.py` (which watches the mirror and tolerates
≤24h export lag).

Differences vs `check_search_events_volume.py`:

| | `check_search_events_volume.py` | `check_search_events_insert_rate.py` (new) |
|---|---|---|
| Source | `analytics_mirror.search_events` (PG) | `logs/analytics.db` `search_events` (SQLite) |
| Floor | `<50 / 24h` | `=0 / 24h` |
| Lag tolerance | ≤24h (waits for nightly export) | ~minutes (writer-side signal) |
| ntfy | never | `--ntfy` ⇒ `INFRA_CRITICAL` |
| Use | weekly auditor confidence in mirror | hourly liveness of the writer |
| Activation | `--grace-until 2026-04-26` (now active) | `--active-from 2026-04-27` (active today) |

Behaviour matrix:

| condition | exit | side effect |
|---|---|---|
| db missing / table missing | 0 | log "advisory" line to stderr |
| `today < active_from` | 0 | log "dormant" status line |
| `count_24h == 0` and active and `--ntfy` | 1 | ntfy `INFRA_CRITICAL` |
| `count_24h == 0` and active, no `--ntfy` | 1 | log WARN line only |
| `count_24h > 0` and active | 0 | log OK line |

### Wiring it into the operator's hourly cadence

Until production is rewired, this check **will fire every run** — that
is the intended signal. Two recommended deployments, depending on how
loud the operator wants the page:

**A. Quiet (no human page, just exit-1 in logs).** Add to an existing
hourly loop (e.g. the worker heartbeat tick):

```bash
PYTHONPATH=/Users/anstudio/agentindex \
  python3 -m smedjan.scripts.check_search_events_insert_rate \
  || echo "[$(date -u +%FT%TZ)] search_events writer still dark" \
       >> /Users/anstudio/smedjan/worker-logs/insert-rate-$(date +%Y-%m-%d).log
```

**B. Loud (page Anders).** Use the `--ntfy` flag. Note that ntfy is
gated by `~/smedjan/config/ntfy_enabled.flag` and `INFRA_CRITICAL` is
on the override-trigger list, so the page goes through even if the
flag is missing:

```bash
PYTHONPATH=/Users/anstudio/agentindex \
  python3 -m smedjan.scripts.check_search_events_insert_rate --ntfy
```

**Recommendation:** ship as variant A until the writer is deployed.
After deploy, flip to B. Otherwise we'll page Anders hourly for a
state he already knows about (the deploy hasn't landed) — a textbook
alert-fatigue setup.

## Outstanding production-deploy ask (`needs_approval`)

To make a synthetic `/search?q=…` produce a row in
`analytics_mirror.search_events` within the export sync window
(acceptance criterion #1), the writer must run inside the LaunchAgent
process. That is a Nerq-prod-affecting change and requires explicit
authority. Suggested minimal-change steps for the deploy operator:

1. From `/Users/anstudio/agentindex` (`main` worktree), cherry-pick
   `cfe675a` (single commit, two files: `agentindex/api/search_events.py`
   new, `agentindex/api/discovery.py` `+ log_search_event(...)` call).
   No schema migration needed — the SQLite table is created
   idempotently on first write.
2. `launchctl kickstart -k gui/$UID/com.nerq.api`.
3. From a different machine, hit
   `https://nerq.ai/search?q=postdeploy-$(uuidgen)` and verify
   `sqlite3 ~/agentindex/logs/analytics.db "SELECT count(*), max(ts) FROM search_events"`
   shows the new row within ~5 seconds.
4. Wait for the next 03:00 `com.nerq.smedjan.analytics_export` run (or
   trigger `~/agentindex/scripts/smedjan-analytics-export.sh` manually)
   and re-check `analytics_mirror.search_events` row count.
5. After the writer is confirmed live, flip the new healthcheck to
   `--ntfy` so a future regression actually pages.

## Acceptance-criteria map

| Criterion | Where | Status |
|---|---|---|
| Synthetic `/search?q=<x>` hit produces a row in `analytics_mirror.search_events` within sync window | requires the cherry-pick + kickstart in §Outstanding production-deploy ask | **blocked on deploy authority** |
| Insert-rate healthcheck configured | `smedjan/scripts/check_search_events_insert_rate.py` (active from 2026-04-27, pages on `count_24h==0`) | **done** |
| Documented in `smedjan/docs/` | this file | **done** |
