# ZARQ Root-Cause Analysis + Fix Roadmap — 2026-05-30

> **Phase 3 of the systematic ZARQ surface audit.** Clusters the 165
> failures from phase 2 (commit `ff3fdf9`) into a small number of root
> causes, cross-references against the five non-zero-exit LaunchAgents,
> and proposes a prioritized fix-roadmap for phase 4. No fixes here.

**Inputs:**
- `tests/zarq_surface/` (current commit `ff3fdf9`)
- `docs/status/zarq_surface_test_run.json` (latest)
- `docs/status/zarq_test_failures_20260530/` (per-failure dumps)
- `docs/status/zarq_surface_inventory_20260530.md` (phase 1)
- `docs/adr/ADR-003a-current-db-topology.md` (DB topology context)

## A) Suite-cleanup summary

Phase 3A removed two waves of suite-quality issues. Commit history:
- `660437e` — 4 fixes per the phase-3A spec (Accept header, /internal skip,
  empty-OK alert tables, redirect cap).
- `ff3fdf9` — 2 additional suite quirks surfaced during the rerun
  (APIRouter prefix-awareness, body truncation before JSON parse).

| Run | PASS | FAIL | SKIP | Total |
|---|---|---|---|---|
| phase 2 initial (`d688227`) | 223 | 226 | 0 | 449 |
| after round-1 suite fixes (`660437e`) | 229 | 209 | 12 | 450 |
| after round-2 suite fixes (`ff3fdf9`) — **baseline** | **287** | **165** | **12** | **464** |

Net suite-cleanup: 61 fewer real failures than the raw phase-2 count, plus
12 paths correctly relabeled SKIP. What remains (165) is the real ZARQ
surface failure surface.

## B) Root-cause clusters

Nine clusters. Each row: cluster ID, one-line root cause, symptom count,
example paths, files / systems touched, risk band, blocking dependencies.

### Cluster R1 — `api.zarq.ai` ingress has no working route to the FastAPI origin

| Property | Value |
|---|---|
| Symptoms | **~60 production-only 404s** (15 crypto_api_v2 + 16 crypto_api_v3 + 14 crypto_agents_api + others) |
| Detail | DNS for `api.zarq.ai` resolves to Cloudflare edge IPs (`104.21.8.47`, `172.67.156.215`) — same as `zarq.ai`. But every path on `api.zarq.ai` returns 404 from the edge, including `/health`. `~/.cloudflared/config.yml` *declares* `api.zarq.ai → http://localhost:8000`, but the Cloudflare-side ingress rule (DNS CNAME to the tunnel, or hostname-to-tunnel binding in the dashboard) is not set. The tunnel never sees `api.zarq.ai` traffic. |
| Verification | `curl https://api.zarq.ai/health` → 404. `curl https://zarq.ai/health` → 200. Same backend per config, very different routing reality. |
| Systems | Cloudflare DNS / tunnel ingress configuration. No application code change required. |
| Risk if fixed | **Low.** Pure DNS / Cloudflare-dashboard config change. No app behavior change. |
| Blocks | Phase-2 production target coverage of every `/v1/*` path. |

### Cluster R2 — `crypto_api.py` router declared but never `include_router`'d

| Property | Value |
|---|---|
| Symptoms | **14 both-target 404s** — `/crypto/rating/{token_id}`, `/crypto/ndd/{token_id}`, `/crypto/ratings`, `/crypto/compare/{token1}/{token2}`, `/crypto/distress-watch`, `/crypto/portfolio/pairs`, `/crypto/portfolio/adaptive`, etc. |
| Detail | `agentindex/crypto/crypto_api.py:41` declares `router = APIRouter(prefix="/crypto", tags=["crypto"])` with 8 GET endpoints. `agentindex/api/discovery.py` never imports this router. Compare: discovery.py:1539-1540 includes `crypto_api_v2.router_v1` and discovery.py:1544-1545 conditionally includes `crypto_api_v3.router_v3`. The legacy v1 router from `crypto_api.py` was orphaned during the v2/v3 refactor. |
| Verification | `grep crypto_api\\. agentindex/api/discovery.py` returns nothing for `from agentindex.crypto.crypto_api`. |
| Systems | `agentindex/api/discovery.py` (one include line) **or** delete `crypto_api.py` if v2/v3 supersede it. **Open question — see F.1.** |
| Risk if fixed | **Low (include) / Low-Medium (delete).** If we include without checking, the `/crypto/*` prefix could collide with `crypto_seo_pages.py` mount at `/crypto`. Worth verifying first. |
| Blocks | Nothing — independent. |

### Cluster R3 — `experiments_api.py` exists but is never mounted

| Property | Value |
|---|---|
| Symptoms | **10 both-target 404s** — `/experiments/dashboard`, `/experiments/dashboard/data`, `/experiments/dashboard/insights`, `/experiments/dashboard/trending/agents`, `/experiments/dashboard/trending/queries`, etc. |
| Detail | `agentindex/experiments/experiments_api.py` (Feb 2026) defines 24 routes. `grep experiments_api agentindex/api/` returns nothing — never imported. The directory is older (mtime: Feb 15) than most active code, suggesting it predates the current routing layout. |
| Verification | `curl http://localhost:8000/experiments/dashboard` → 404. |
| Systems | `agentindex/api/discovery.py` (one include) **or** delete the file. **Open question — see F.2.** |
| Risk if fixed | **Low.** If we include, routes appear; if we delete, no behavior change. |
| Blocks | Nothing. |

### Cluster R4 — `/weekly` + `/v1/agent/weekly` Internal Server Error (transient)

| Property | Value |
|---|---|
| Symptoms | **2 localhost 500s in phase-2 initial run.** Re-runs show `/weekly` → 200 (HTML response) and `/v1/agent/weekly` flapping. |
| Detail | `agentindex/weekly_signal.py:11` defines `router_weekly = APIRouter(tags=["weekly"])`. Routes `@router_weekly.get("/v1/agent/weekly")` and `@router_weekly.get("/weekly", response_class=HTMLResponse)`. The 500s correlated with the morning's PgBouncer saturation. Now passes; the failure mode is intermittent. |
| Verification | `curl http://localhost:8000/weekly` → 200 with 18 KB HTML (post-fix-window). Earlier this morning the same endpoint returned 500. |
| Systems | `agentindex/weekly_signal.py` for any uncaught exceptions; PgBouncer pool health (broader cluster R7). |
| Risk if fixed | **Medium.** Hard to fix without reproducing — would need to read the exception path and add explicit error handling. Without a 500 in hand, fix is speculative. |
| Blocks | Nothing. |

### Cluster R5 — Dashboard `/action/*` endpoints 404

| Property | Value |
|---|---|
| Symptoms | **6 both-target 404s** — `/action/approve`, `/action/reject`, `/action/dismiss`. |
| Detail | These look like admin / moderation actions in `agentindex/dashboard.py`. Investigating whether they're declared on a router that's gated behind admin auth + not included publicly. Possibly an old admin-only interface. |
| Verification | `curl http://localhost:8000/action/approve` → 404. |
| Systems | `agentindex/dashboard.py` — declare router or remove dead code. **Open question — see F.3.** |
| Risk if fixed | **Medium.** If these are admin write endpoints, mounting them without auth = real exposure risk. Better to gate-then-mount than mount-blindly. |
| Blocks | Nothing. |

### Cluster R6 — `/zarq/dashboard` requires auth (401)

| Property | Value |
|---|---|
| Symptoms | **4 both-target 401s** — `/zarq/dashboard`, `/zarq/dashboard/data`. |
| Detail | The dashboard requires a key (similar pattern to the `/internal/*` skip in cluster suite-cleanup). The test suite hits these and expects 200 because the route exists in code; the runtime gates them. Should probably be added to `_OUT_OF_SCOPE_PREFIXES`. |
| Verification | `curl http://localhost:8000/zarq/dashboard` → 401. |
| Systems | Test suite only — add `/zarq/dashboard` to the out-of-scope prefix list. Not a ZARQ bug; a suite-scope item. |
| Risk if fixed | **Trivial.** Suite-only change. |
| Blocks | Nothing. |

### Cluster R7 — Endpoints that time out under PgBouncer pressure

| Property | Value |
|---|---|
| Symptoms | **5 TIMEOUT failures.** Examples: `/dashboard/data` (both targets), `/citation-dashboard` (localhost), `/internal/yield` (production), `/v1/intelligence/agent/{agent_name}/dashboard` (localhost), `/feed/cve-alerts.xml` (localhost). |
| Detail | These endpoints query Postgres and hit either (a) the inactive `mac_studio_slot` standby replication path, (b) PgBouncer `query_wait_timeout` queuing, or (c) the missing-cache fallback (cluster R8). The fingerprint matches the morning's PgBouncer saturation pattern (24 `query_wait_timeout` events between 09:00 and 10:00; 16 more between 10:30 and 11:30). |
| Verification | PgBouncer log entries directly correlate with API error log entries. |
| Systems | PostgreSQL on Nbg (memory pressure, see ADR-003a issue 2), PgBouncer pool sizing, possibly the endpoint queries themselves. |
| Risk if fixed | **High.** Touching PgBouncer config (pool size, query_wait_timeout) is the same class of change that caused the 2026-05-30 morning outage. Memory pressure fix on Nbg is also risky — restarting Patroni is what caused the OOM-loop. Needs ADR-003a issue 1 + 2 resolved first. |
| Blocks | Some symptoms in clusters R8 and R9 may resolve when R7 resolves. |

### Cluster R8 — Cache-builder LaunchAgents dead → endpoints serve from slow path

| Property | Value |
|---|---|
| Symptoms | Likely contributes to **2 of the 5 TIMEOUT failures in R7**. Specifically `/dashboard/data` and `/citation-dashboard`. |
| Detail | Two LaunchAgents that produce cached responses are in `exit≠0`: `com.nerq.zarq-cache` (exit=2, builds `/tmp/zarq_dashboard_cache.json`) and `com.nerq.dashboard-data` (exit=1). When the endpoint can't find its cache file, the in-line fallback runs the slow Postgres query — which then triggers R7's timeout. Not provable from the suite alone; correlation only. |
| Verification | `ls /tmp/zarq_dashboard_cache.json` → file exists OR is missing. The cache-warmer (`com.nerq.dashboard-cache-warmer`, pid=23210, exit=0) is running, but that's a different agent for a different cache. The relevant ones are `zarq-cache` and `dashboard-data`. |
| Systems | `scripts/refresh_zarq_dashboard_cache.py` (the one `com.nerq.zarq-cache` runs), `scripts/dashboard_data.*` or equivalent, and the endpoints in `agentindex/zarq_dashboard.py`. |
| Risk if fixed | **Medium.** Restarting the LaunchAgents is low risk; understanding *why* they exit-2 / exit-1 requires reading their stderr logs and may surface deeper code issues. |
| Blocks | R7 partially. |

### Cluster R9 — `/vitality` production path: occasional 8+ second slowness

| Property | Value |
|---|---|
| Symptoms | **1 CLOUDFLARED_GAP failure** (down from 5 in the round-1 rerun). Localhost: 4 seconds. Production: timeout at 8 seconds. Same backend. |
| Detail | Both the localhost and production paths terminate at uvicorn :8000. The production path goes through Cloudflare edge first, which adds round-trip latency + possible cold-start. The 4-second local response is itself slow — the *production* added time pushes past the suite's 8-second wall. |
| Verification | `/vitality` works locally but exceeds 8s wall via Cloudflare. |
| Systems | Endpoint code in `agentindex/crypto/zarq_vitality_page.py` + PgBouncer behavior under load. Same risk profile as R7. |
| Risk if fixed | **Medium-High.** Optimizing the endpoint requires touching the vitality query; the production-only slowdown is partially network. |
| Blocks | Nothing. |

### Cluster R10 — NETWORK_ERROR / PARSE_ERROR remnants

| Property | Value |
|---|---|
| Symptoms | **4 NETWORK_ERROR + 0 PARSE_ERROR** (PARSE_ERROR fixed by suite cleanup). Examples: MCP "Connection reset by peer", `/crypto` localhost timeout. |
| Detail | Transient. Likely flap caused by uvicorn restart cycles or PgBouncer-induced backend resets during the test run. |
| Verification | Re-running these in isolation typically passes. |
| Systems | None directly; manifestations of R7 / API restart-loop. |
| Risk if fixed | **N/A.** No direct fix; resolves when R7 / API stability resolves. |
| Blocks | Nothing. |

## C) Dependency graph between clusters

```
                        ┌──────────────────────────────────────┐
                        │ ADR-003a issue 1: Patroni dead       │
                        │ ADR-003a issue 2: Nbg OOM pressure   │
                        └────────────────┬─────────────────────┘
                                         │ enables
                                         ▼
                              ┌─────────────────────┐
                              │  R7 PgBouncer load  │◀───────┐
                              │  → TIMEOUT cluster  │         │ partially caused by
                              └────────┬────────────┘         │
                                       │ contributes to       │
                                       ▼                      │
                              ┌─────────────────────┐         │
                              │  R8 cache-builder   │─────────┘
                              │  agents dead        │
                              └─────────────────────┘
                                       │ overlaps with
                                       ▼
                              ┌─────────────────────┐
                              │  R9 /vitality slow  │
                              │  on production      │
                              └─────────────────────┘

                              R1  api.zarq.ai ingress      ◀── independent
                              R2  crypto_api.py orphan     ◀── independent
                              R3  experiments_api.py orphan◀── independent
                              R4  /weekly transient 500    ◀── transient, partially R7
                              R5  /action/* 404            ◀── independent
                              R6  /zarq/dashboard 401      ◀── suite scope, not a bug
                              R10 NETWORK transient        ◀── transient, partially R7
```

R1, R2, R3, R5, R6 are independent and can be fixed in any order. R7 and
its downstream (R8, R9, R10) are coupled with the ADR-003a HA work and
should not be touched until that lane is unblocked.

## D) Prioritized fix roadmap for phase 4

Sorted by `(blast_radius / risk)`. Highest leverage at the top.

| Prio | Cluster | Effort | Blast radius | Risk | Approach (1–3 sentences) | Verification test |
|---|---|---|---|---|---|---|
| 1 | **R1** — `api.zarq.ai` ingress | S | ~60 production 404s | **Low** | Add DNS CNAME or Cloudflare Zero-Trust hostname binding for `api.zarq.ai` → the same tunnel currently serving `zarq.ai`. Test by curl-ing `api.zarq.ai/health` and expecting 200. | `tests/zarq_surface/test_cloudflared_routes.py::test_cloudflared_parity[api_rating_btc]` should flip to pass. |
| 2 | **R6** — Suite scope: `/zarq/dashboard` 401 | S | 4 failures | **Trivial** | Add `/zarq/dashboard` and `/zarq/dashboard/` to `_OUT_OF_SCOPE_PREFIXES` in `test_http_endpoints.py`. Pure suite update. | Suite reruns; 4 fewer FAIL, 4 more SKIP. |
| 3 | **R2** — `crypto_api.py` orphan | S | 14 both-target 404s | **Low-Medium** | **DECISION REQUIRED (F.1).** Either include the router in discovery.py (4-line change) or delete the file (one rm). | `/crypto/rating/bitcoin` returns 200, all 14 routes pass on both targets. |
| 4 | **R3** — `experiments_api.py` orphan | S | 10 both-target 404s | **Low** | **DECISION REQUIRED (F.2).** Mount or delete the module. | `/experiments/dashboard` returns 200, or routes disappear from discovery list. |
| 5 | **R5** — `/action/*` 404 | M | 6 failures | **Medium** | **DECISION REQUIRED (F.3).** Determine whether these are dead admin code or genuine missing endpoints; gate behind auth if mounted. | `/action/approve` returns either 401 (gated) or 200 (mounted with proper handler). |
| 6 | **R4** — `/weekly` transient 500 | M | 2 failures, intermittent | **Medium** | Capture a 500 in the wild (the test currently sees 200). Until reproducible, the fix is speculative — add explicit exception handling around the DB queries in `weekly_signal.py` and log the cause. | Stress-test `/weekly` 100 times in a row; observe ratio of 5xx to 2xx. Should be 0%. |
| 7 | **R8** — Cache-builder LaunchAgents | M | Probably 2 of the 5 TIMEOUTs in R7 | **Medium** | Read stderr logs for `com.nerq.zarq-cache` and `com.nerq.dashboard-data`. Fix whatever is causing exit-2 / exit-1. Re-enable and verify cache files appear under `/tmp/`. | Cache files exist + endpoints respond <1s. |
| 8 | **R9** — `/vitality` production slow | M | 1 failure (was 5) | **Medium-High** | Profile the vitality query; consider adding an index or caching. Touches PgBouncer/Nbg, so the risk band overlaps R7. | `/vitality` localhost <1s, production <3s consistently. |
| 9 | **R7** — PgBouncer load → TIMEOUT | L | 5 failures + R8, R10, R4 partial | **High** | Resolve ADR-003a issues 1 (Patroni dead) and 2 (Nbg OOM pressure) first. Then revisit pool sizing and `query_wait_timeout`. **Do not touch the PgBouncer config without the HA work in place.** | TIMEOUT cluster drops to 0 sustained; `query_wait_timeout` log <1/hour. |
| 10 | **R10** — NETWORK transient | — | 4 (transient) | N/A | Will resolve when R7 resolves. No direct work. | Re-run reveals 0 NETWORK_ERROR sustained. |

**Phase 4 first move:** R1. Single config change, ~60 symptoms drop.
Verification is the existing test suite re-run.

## E) Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Restarting Patroni triggers another OOM-loop on Nbg** (ADR-003a issue 1+2 path) | High | Critical — repeat of 2026-05-30 morning outage | Before any Patroni action, follow the prerequisites listed in ADR-003a section 5 |
| **Including `crypto_api.py` router conflicts with `crypto_seo_pages.py` at `/crypto`** | Medium | Medium — could shadow HTML routes with JSON routes | F.1 decision must verify prefix collision; mounting order matters |
| **`api.zarq.ai` DNS change propagates slowly** | Low | Low — minutes to hours | Make change ahead of next release window; verify with `dig` from outside the network |
| **Mounting `experiments_api.py` exposes endpoints that were intentionally hidden** | Medium | Medium — depends on what they do | F.2 decision: read the file first |
| **Mounting `/action/*` exposes write endpoints without auth** | Medium | High — moderation/approval endpoints could be abused | F.3 decision: gate first, mount second |
| **The morning's API instability persists during phase 4 work** | Medium | Medium — test signals harder to read | Re-run smoke after each fix; if API restart count climbs, pause |
| **Suite false negatives mask real bugs after suite changes** | Low | Medium — would shrink visible regression surface | Keep both the cleaned baseline (165 fails) and the more-permissive raw discovery in CI to triangulate |

## F) Open questions for Anders

These must be decided before the corresponding cluster can be fixed.

### F.1 — `crypto_api.py`: include, delete, or merge into v2/v3?

The file is 8 GET endpoints with `prefix="/crypto"`. The newer
`crypto_api_v2.py` (`/v1/crypto`) covers most of the same domain. Options:

  a. **Include it** — adds `/crypto/rating/{token_id}` etc. as a stable
     alias for older clients. Risk: prefix collision with the
     `crypto_seo_pages.py` mount at `/crypto`.
  b. **Delete it** — accept that `/v1/crypto/*` is the only ZARQ API
     surface. Any external client still calling `/crypto/*` breaks.
  c. **Merge it into v2** — copy non-duplicate endpoints over; delete
     the file. Higher refactor effort but cleanest end state.

### F.2 — `experiments_api.py`: mount or delete?

24 routes under `/experiments/*` including dashboards and trending queries.
Last modified Feb 2026 — clearly predates the current architecture. Mount,
mount-with-auth, or delete?

### F.3 — `/action/*` endpoints (`dashboard.py`): live admin or dead code?

`/action/approve`, `/action/reject`, `/action/dismiss` — these look like
moderation queue actions. Are they:

  a. **Live admin endpoints** that should be mounted behind auth?
  b. **Dead code** from an earlier moderation flow that's been replaced?
  c. **Used internally by another process** (e.g. an admin UI that's not
     part of this repo)?

### F.4 — `api.zarq.ai` vs `api.nerq.ai`: revive both, just one, or collapse to `zarq.ai`?

`api.nerq.ai` has no DNS at all (the suite saw `curl: (6) Could not resolve
host`). `api.zarq.ai` has DNS but no edge-to-origin routing. Cloudflared
config declares both. Do we want both alive as `api.*` subdomains? Or
collapse to using `zarq.ai`/`nerq.ai` directly?

### F.5 — Suite scope: which auth-gated paths are out-of-scope?

Currently `/internal/*` is skipped (commit `660437e`). `/zarq/dashboard*`
likely should be added. What's the policy — do we add a key/header to
the suite (which would test full surface but require key management), or
exclude auth-gated paths entirely from the public-surface suite?

## Out-of-scope for phase 3

- Actually fixing any failure (phase 4).
- Touching PgBouncer config (R7 — risk-managed in phase 4 only after
  ADR-003a HA prerequisites).
- Suite-quality "round 3" fixes beyond the two rounds already shipped
  (`660437e` + `ff3fdf9`).
- Mounting/unmounting routers without decision per F.1/F.2/F.3.
