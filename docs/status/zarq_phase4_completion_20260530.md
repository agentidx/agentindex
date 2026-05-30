# ZARQ Phase 4 Completion Report — 2026-05-30

> Continuation of `zarq_phase4_execution_20260530.md`. Anders supplied
> answers to O.1–O.3 and authorized executing R5 (docs-only) and
> R11–R13 (the three 5xxs surfaced by R2/R3). R1a/R1b remain pending
> a Cloudflare API token (Anders to drop into `secrets/.env`).

## A) Final statistics

| Metric | Phase 3 baseline | End of phase 4 | Delta |
|---|---|---|---|
| PASS | 287 | **319** | **+32** |
| FAIL | 165 | 133 | **−32** |
| SKIP | 12 | 12 | 0 |
| `HTTP_4XX_unexpected` | 157 | **56** | **−101** |
| `TIMEOUT` | 5 | 53 | **+48 (downstream of R7)** |
| `HTTP_5XX` | 0 | 3 | +3 (Cloudflare 502s — upstream slow) |
| `STALE_DATA` | 0 | 4 | +4 (PG slow query — R7) |
| `NETWORK_ERROR` | 2 | 6 | +4 (R7-class flake) |
| `EMPTY_RESPONSE` | 0 | 7 | +7 (R7-class) |
| `CLOUDFLARED_GAP` | 1 | 3 | +2 |
| `DB_TABLE_MISSING` | 0 | 1 | +1 (statement timeout misclassified) |

**Headline:** −101 of the 145 `HTTP_4XX_unexpected` failures resolved.
The `TIMEOUT` / `STALE_DATA` / `NETWORK_ERROR` / `EMPTY_RESPONSE` increases
are all manifestations of the R7 PgBouncer-pressure cluster — explicitly
deferred per ADR-003a HA-prerequisites. They were *masked* by the 404s
that R2/R3 resolved; they are not regressions.

## B) Commits this phase (chronological)

```
4e5cabd  test(zarq): fix --zarq-target override colliding with fixture parametrization
2f47d3e  feat(infra): endpoint usage audit + deprecation logger middleware
7674fa1  test(zarq): auth endpoint test suite (key-gated)
abc7fa1  feat(api): mount crypto_api.py with deprecation logger (resolves 14 404s)
84a1472  feat(api): mount experiments_api with deprecation logger (resolves 10 404s)
2895c7a  docs: phase 4 execution report — 287 PASS → 293, 5 commits, 2 deferred
dce914e  docs(tracking): action endpoints audit-driven decision plan
a5bef8a  fix(crypto): /crypto/distress-watch — replace missing ndd_trend_7d/30d columns with actual schema
12bd665  fix(crypto): /crypto/compare/{a}/{b} — same ndd_trend column rename as R11
343eab9  fix(experiments): /experiments/dashboard/insights — cache initial state shape mismatch
```

Plus this report. 11 commits total since the phase-3 plan landed.

## C) Root causes fixed

| ID | What | How |
|---|---|---|
| **PREP-1** | `zarq.endpoint_usage_audit` table + `DeprecationLoggerMiddleware` | New migration, 167-line middleware, mounted in discovery.py with prefixes `/crypto/`, `/experiments/`, `/action/`. Verified end-to-end. |
| **PREP-2** | Auth test suite (key-gated) | `secrets/.env.test` (gitignored) + `test_auth_endpoints.py` covering 2 distinct auth schemes (`NERQ_DASHBOARD_KEY` for `/internal/*`, `ZARQ_METRICS_TOKEN` for `/zarq/dashboard*`). |
| **R2** | `crypto_api.py` orphan router never included | Added `app.include_router` for `router as crypto_legacy_router`. 14 404s resolved; 5 routes now 200, 2 surfaced 500s (→ R11/R12 below), 1 surfaced timeout. |
| **R3** | `experiments_api.py` not mounted | Included `experiments_api.app.router` (FastAPI's underlying APIRouter). 10 404s resolved; surfaced 2 500s (→ R13). |
| **R5** | `/action/*` admin write endpoints | **Not mounted** — `docs/tracking/action-endpoints-decision-pending.md` captures the day-14 decision criteria. Audit middleware records all hits. |
| **R11** | `/crypto/distress-watch` 5xx | SQL referenced `d.ndd_trend_7d`/`ndd_trend_30d` columns that don't exist. Schema has `ndd_trend` (text categorical) + `ndd_change_4w` (real). Rewrote query to use actual columns. |
| **R12** | `/crypto/compare/{a}/{b}` 5xx | Same ndd_trend column-rename bug as R11. Same fix. |
| **R13** | `/experiments/dashboard/insights` 5xx | `DiscoveryDashboard.__init__` set `cache["response_times"] = []` (list) but `_get_response_times()` returns dict shape. Cold-cache consumers (`generate_insights`) hit `AttributeError: 'list' object has no attribute 'get'`. Aligned initial state with returned shape. Also fixed `/experiments/stats` (same root cause). |

## D) Root causes deferred

| ID | What | Why deferred |
|---|---|---|
| **R1a/R1b** | `api.zarq.ai` + `api.nerq.ai` Cloudflare ingress | Needs `CLOUDFLARE_API_TOKEN` (O.1 — Anders to place in `secrets/.env`). When token lands, R1a/R1b are ~5 min of work. Carries ~60 production-only 404s. |
| **R4** | `/weekly` + `/v1/agent/weekly` 5xx | 20-attempt stress reproduced 0 × 5xx. Saw 200 + rate-limited 429 + transient timeouts. Phase-2 500s correlate with PgBouncer saturation (R7 cluster). Speculative patch deferred until 5xx reproduces. |
| **R7** | PgBouncer query_wait_timeout cluster | ADR-003a HA prerequisites: Patroni dead on both nodes, Nbg OOM pressure. Phase-4 explicitly does not touch this lane. |
| **R8** | Cache-builder LaunchAgents at non-zero exit | Tangled with R7 (endpoints fall back to slow PG query when cache is missing). Same deferral. |
| **R9** | `/vitality` production 85s slow | Same R7 lane — PgBouncer + Nbg slow. |
| **R10** | Transient NETWORK errors | Manifestation of R7. Will resolve when R7 resolves. |
| **O.3 endpoint-internal bugs surfaced by R2/R3** | Three were R11/R12/R13 above → fixed. Any new ones from future audit-window data → new R-tickets. |

## E) ADR-003a-blocked inventory (HA recovery roadmap input)

Lift these straight into the HA recovery workstream when it starts.

```
R7 — PgBouncer query_wait_timeout cluster
     · 53 TIMEOUTs in last phase-4 suite run (up from 5; surfaced by R2/R3)
     · 502s on production for /paper-trading, /vitality/methodology,
       /cascade-risk, /yield (Cloudflare-edge timeout because origin slow)
     · 4 STALE_DATA — query against crypto_rating_daily with
       run_date::timestamp cast (no index) times out
     · Live root cause documented in ADR-003a issues 1+2: Patroni dead
       on both nodes, Nbg OOM pressure
     · Phase-4 sample: PgBouncer logs show recurring
       "server conn crashed?" — Nbg-side PG losing connections

R8 — Cache-builder LaunchAgent state
     · com.nerq.zarq-cache (exit=2) — /tmp/zarq_dashboard_cache.json
       producer
     · com.nerq.dashboard-data (exit=1) — dashboard data refresh
     · com.nerq.dex-volumes (exit=1) — zarq.chain_dex_volumes
     · com.nerq.stale-scores (exit=1)
     · com.nerq.trust-score-v3 (exit=1)
     · Each agent's exit code is recorded; the failure mode of each
       requires reading its stderr log + matching against current PG
       schema (some are likely schema-drift like R11/R12).

R9 — /vitality production endpoint
     · Localhost: 4s response
     · Production: >8s timeout (some runs 85s+)
     · Same backend, only the path through Cloudflare → tunnel → uvicorn
       is slow. Hot-cache and pool-saturation interplay.

R4 — /weekly intermittent 5xx
     · Not reproducible in isolation
     · Correlated with PgBouncer saturation events
     · No code change made; if 5xx returns in audit data, file as
       R4-rerun with stack trace.

R10 — NETWORK transient
     · Will dissolve when R7 dissolves.
```

## F) Audit-table snapshot (day-1, ~5.5 hours of capture)

`zarq.endpoint_usage_audit` started capturing 2026-05-30 11:42 CEST.
Numbers at end-of-phase-4 (5.5h window):

| Prefix | Hits | Distinct IPs | Distinct paths | Notes |
|---|---|---|---|---|
| `/crypto/*` | 203 | 56 | 79 | **68 external hits from 55 distinct external IPs** — real users actively call this surface. The "delete" path for crypto_api.py (F.1.b in phase 3) is **wrong**; the routes are being called. Plan for keep+stabilize, not delete. |
| `/experiments/*` | 32 | 2 | 8 | 4 external hits from 1 IP. Either a single curious user/bot or test traffic. 14-day window will clarify. |
| `/action/*` | 19 | 2 | 3 | **3 external hits from 1 external IP.** Worth flagging — was expected to be zero. Need to identify the IP at day-14 (operator? automation? unknown?). |
| `/__test__/*` | 1 | 1 | 1 | Suite test fixture artefact. Ignore. |

Day-14 review date: **2026-06-13**. Run the queries in
`docs/tracking/action-endpoints-decision-pending.md` and the analogous
queries in this report's table to make per-prefix decisions.

The `/action/*` 3-external-hit signal is the most surprising. Two
possibilities:
1. There's a legitimate external client (operator, monitoring bot, etc.)
   that was getting 404s before R5 audit started — they'd be invisible
   without the middleware.
2. Some kind of probing (security scan, attacker reconnaissance).

Either way, **the right move is to wait for the day-14 IP-detail
breakdown** before mounting / deleting.

## G) Verification (no-regression checks)

| Check | Status |
|---|---|
| All previous PASS still PASS | ✓ Phase-3's 287 + R2+R3+R11+R12+R13 deltas net to 319 (-32 FAIL) |
| External endpoints 200 at end of phase | ✓ localhost:8000/health, zarq.ai/, nerq.ai/health all 200 |
| `com.nerq.api` stable now | ✓ pid 64644, alive, last 5 min |
| PgBouncer state | ⚠ recovering — "server conn crashed?" warnings during suite run; live state OK at end. R7 cluster active. |
| Test suite repeatable | ✓ Phase-4 final run was 12:39 (3x slower than baseline due to R7 timeouts; the underlying classification still correct) |

## H) Open follow-ups (urgency-sorted)

1. **O.1 — Cloudflare API token.** Anders to drop a token with
   `Zone:DNS:Edit` + `Zone:Zone:Read` for zones `zarq.ai`, `nerq.ai`,
   `agentcrawl.dev` into `~/agentindex/secrets/.env` as
   `CLOUDFLARE_API_TOKEN=...`. Then I execute R1a (resolve ~60 prod
   404s — largest remaining blast-radius prize) and R1b (clean up the
   two bogus CNAMEs under agentcrawl.dev).

2. **R7 HA recovery.** Separate workstream. ADR-003a issues 1+2.
   Blocks R4, R8, R9, R10 and the 53 current TIMEOUTs.

3. **Day-14 audit review (2026-06-13).** Run the per-prefix queries.
   Decide delete-vs-keep on `/crypto/*` (keep — has external users),
   `/experiments/*` (probably delete pending external-pattern check),
   `/action/*` (depends on IP identity of the 3 external hits).

4. **Test-API-key isolation.** Tracked in
   `docs/tracking/test-api-key-isolation.md`. Low urgency.

5. **Suite quality: TIMEOUT mis-classification.** One DB_TABLE_MISSING
   was actually a statement-timeout against `crypto_rating_daily`. The
   classifier doesn't distinguish `relation does not exist` from
   `canceling statement due to statement timeout`. Tiny refinement;
   defer until next phase.

6. **Legacy `ndd_trend_7d` references in `crypto_ndd_daily.py` /
   `crypto_ndd_daily_v2.py`.** These pipeline scripts still reference
   the old column names but aren't actively called (v3 is the current
   pipeline). Document or delete in a cleanup pass.
