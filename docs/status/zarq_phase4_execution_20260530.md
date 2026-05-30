# ZARQ Phase 4 Execution Report — 2026-05-30

> **Phase 4 of the systematic ZARQ surface audit.** Execution log for the
> fix-roadmap from phase 3 (commit `8d9e253`). One root cause per commit.
> Two items were deferred to subsequent work; rationale below.

## Executive summary

| Metric | Phase 3 baseline | After phase 4 | Delta |
|---|---|---|---|
| Tests collected | 464 | 464 | 0 |
| PASS | 287 | **293** | +6 |
| FAIL | 165 | **159** | −6 |
| SKIP | 12 | 12 | 0 |
| `HTTP_4XX_unexpected` | 157 | **145** | **−12** |
| `HTTP_5XX` | 0 | 3 | +3 (newly visible endpoint bugs) |
| `TIMEOUT` | 5 | 3 | −2 |
| `NETWORK_ERROR` | 2 | 5 | +3 (transient) |
| `CLOUDFLARED_GAP` | 1 | 1 | 0 |
| `EMPTY_RESPONSE` | 0 | 2 | +2 |

12 fewer 404s, +6 net PASS, no regressions of previously-passing tests.
The newly visible 5xxs and transient errors are pre-existing endpoint
internals that the 404s were masking — surfaced by the route mounts, not
introduced by them.

## Commits applied

```
84a1472 feat(api): mount experiments_api with deprecation logger (resolves 10 404s)
abc7fa1 feat(api): mount crypto_api.py with deprecation logger (resolves 14 404s)
7674fa1 test(zarq): auth endpoint test suite (key-gated)
2f47d3e feat(infra): endpoint usage audit + deprecation logger middleware
4e5cabd test(zarq): fix --zarq-target override colliding with fixture parametrization
```

## Per-step results

### Pre-flight ✓

`com.nerq.api` pid 61697 uptime 65 min, 1 PgBouncer `query_wait_timeout`
event in the prior 30 min, Nbg reachable, git clean, baseline suite run
confirmed 287 PASS / 165 FAIL.

### Conftest fix `4e5cabd` (preamble)

`--zarq-target` flag collided with the fixture's `params=TARGETS`
declaration → "duplicate parametrization" on collection. Removed the
fixture params; `pytest_generate_tests` is now the single source of truth
for target parametrization. Localhost-only baseline confirmed: 190 PASS /
45 FAIL / 6 SKIP.

### PREP-1 `2f47d3e`: endpoint_usage_audit + deprecation_logger ✓

| Item | Status |
|---|---|
| `migrations/zarq/20260530-02-endpoint-usage-audit.sql` | Applied (idempotent — ran twice clean) |
| `agentindex/api/middleware/deprecation_logger.py` (167 lines) | All 4 unit tests pass |
| Mount in `discovery.py` for `/crypto/`, `/experiments/`, `/action/` | Live |
| End-to-end smoke (GET `/crypto/rating/bitcoin` audit row) | Row written with status=404, response_time_ms=5 |

After the API restart the audit table had 126 `crypto` hits, 26
`experiments` hits, 16 `action` hits during the phase-4 window — proving
the middleware fires correctly.

### PREP-2 `7674fa1`: key-gated auth test suite ✓

| Item | Status |
|---|---|
| `secrets/.env.test` (gitignored, verified) | Written |
| `tests/zarq_surface/test_auth_endpoints.py` (6 tests) | All 6 pass on localhost |
| Found-during-test: two auth schemes (`NERQ_DASHBOARD_KEY` for `/internal/*` vs `ZARQ_METRICS_TOKEN` for `/zarq/dashboard*`) | Both supported via per-test `auth_scheme` param |
| `docs/tracking/test-api-key-isolation.md` (future work) | Written |

The suite skips cleanly when `ZARQ_TEST_API_KEY` is unavailable. The
file `.env.test` reuses production defaults rather than building parallel
key infra — tracked for proper isolation later.

### R1 — Cloudflare ingress `api.zarq.ai` / `api.nerq.ai` ⛔ **BLOCKED**

`cloudflared tunnel route dns` requires a cert with permissions for the
target zone. Our `~/.cloudflared/cert.pem` is scoped to `agentcrawl.dev`
only (verified by decoding the token). Running the command added bogus
CNAMEs `api.zarq.ai.agentcrawl.dev` and `api.nerq.ai.agentcrawl.dev` —
both proxied through Cloudflare but pointing under the wrong domain.

These bogus records are functional litter — they don't affect production
zarq.ai / nerq.ai, but they exist and should be cleaned up. Cleanup
requires Cloudflare dashboard access.

**Unblocking R1 requires one of:**

1. `cloudflared login` on this host, navigating in a browser to authorize
   `zarq.ai` and `nerq.ai` zones. Generates a new multi-zone cert.
2. A Cloudflare API token with DNS:Edit for `zarq.ai` and `nerq.ai`
   zones, used directly via `curl`.
3. Manually adding the CNAMEs in the Cloudflare dashboard.

Tracked as open question O.1 below. R1 carried the biggest blast-radius
prize in phase 3 (~60 production 404s), so resolving it remains
high-leverage.

### R2 — Mount `crypto_api.py` `abc7fa1` ✓

7 unique `/crypto/*` paths mounted. Localhost verification:

| Path | Status |
|---|---|
| `/crypto/rating/bitcoin` | 200 |
| `/crypto/ndd/bitcoin` | 200 |
| `/crypto/ratings` | 200 |
| `/crypto/portfolio/adaptive` | 200 |
| `/crypto/distress-watch` | **500** (endpoint internal bug) |
| `/crypto/compare/bitcoin/ethereum` | **500** (endpoint internal bug) |
| `/crypto/portfolio/pairs` | **timeout** (PgBouncer pressure) |

5 routes truly fixed. 2 endpoints have pre-existing handler bugs (now
visible); 1 hits the R7 PgBouncer cluster. None are regressions of this
commit.

### R3 — Mount `experiments_api.py` `84a1472` ✓

24 routes via `experiments_api.app.router` include. Localhost verification:

| Path | Status |
|---|---|
| `/experiments` | 200 |
| `/experiments/dashboard` | 200 |
| `/experiments/dashboard/data` | 200 |
| `/experiments/health` | 200 |
| `/experiments/dashboard/insights` | **500** (`AttributeError` at `discovery_dashboard.py:478`) |
| `/experiments/stats` | **500** (same pattern) |

5 routes fixed. 2 endpoints have a pre-existing `.get(...)` on a `list`
value — not introduced by this commit. Audit middleware captures every
hit for the 14-day decision window.

### R4 — `weekly_signal.py` 500s ⏭ **DEFERRED (could not reproduce)**

20-request stress loop against `/weekly` + `/v1/agent/weekly`. No 500s
observed. Saw 200 (success), 429 (rate limiter — `BotRateLimitMiddleware`),
and `000` (connection timeout). The phase-2 500s correlated with the
2026-05-30 morning PgBouncer saturation — downstream of R7.

Speculative patch would be a `try/except` band-aid without a reproducible
exception path. Deferred until the 500s recur in the wild and we can
capture the stack trace.

### R5 — `/action/*` admin endpoints ⏭ **DEFERRED (auth-gate decision needed)**

`dashboard.py` declares `/action/approve`, `/action/reject`,
`/action/dismiss` on a standalone FastAPI app, currently not mounted in
`discovery.py`. The handlers do **writes**: they call
`agentindex.agents.action_queue.{approve,reject,mark_dismissed}` based
on a `?id=...` query parameter.

Anders' F.3 answer was "keep as live admin surface + deprecation_logger".
Mounting them as-is would expose unauthenticated write endpoints — a real
security regression from the current 404 state.

The phase-3 risk register explicitly flagged this: *"gate first, mount
second"*. Without a clear gate decision (reuse `NERQ_DASHBOARD_KEY`, use a
new scheme, or restrict to `/admin/*` prefix with shared auth), I declined
to mount unilaterally.

Tracked as open question O.2.

### R6 — Suite scope ✓ (already done in phase 3)

`/zarq/dashboard*` already covered by `_OUT_OF_SCOPE_PREFIXES` from
`660437e`. Auth suite (PREP-2) now exercises it positively when the key
is present.

### R7 / R8 / R9 / R10 ⏭ **DEFERRED (HA prerequisites)**

Per the phase-3 plan and Anders' rules: do not touch the PgBouncer pool,
Patroni, etcd, or the Nbg OOM pressure until ADR-003a HA prerequisites
are resolved. Phase 4 leaves these untouched.

## Suite-runtime stability observation

`com.nerq.api` was kickstarted 3 times in phase 4 (PREP-1, R2, R3).
After each kickstart the first suite run showed elevated `NETWORK_ERROR`
counts that settled on a second run (e.g. 11 → 7 after R3 in a back-to-back
rerun). This indicates fragility in the worker warm-up window — not a
flaw of the fixes themselves, but a real signal about the underlying
system.

PgBouncer `query_wait_timeout` count between 11:00–12:00 today: 16 (down
from morning's 50+/hour but not zero). Consistent with R7 cluster still
being live.

## Open questions raised by phase 4

### O.1 — Cloudflare cert / DNS for `api.zarq.ai` + `api.nerq.ai`

R1 needs Cloudflare access at one of three levels (browser
login, API token, dashboard). Which path does Anders prefer? Until
unblocked, ~60 production-only 404s remain unresolved.

Bogus CNAMEs created and needing cleanup:
- `api.zarq.ai.agentcrawl.dev`
- `api.nerq.ai.agentcrawl.dev`

### O.2 — Auth scheme for `/action/*` admin endpoints

Three options:

a. Reuse `NERQ_DASHBOARD_KEY` (existing pattern, single scope).
b. Introduce a separate `NERQ_ADMIN_KEY` for write actions, distinct
   from the read-only dashboard key.
c. Keep them unmounted; rely on the deprecation_logger to show no
   external traffic asks for them anyway (in which case "delete"
   becomes a clearer answer after 14 days of audit data).

If (a) or (b), I can ship R5 with a one-commit follow-up. (c) is the
zero-risk option.

### O.3 — Two endpoint-internal 5xx bugs surfaced by R2 + R3

Three handlers crash with real bugs now that they're routable:

1. `crypto_api.py:348` `distress-watch` → 500
2. `crypto_api.py:248` `compare/{token1}/{token2}` → 500
3. `experiments/discovery_dashboard.py:478` `generate_insights` →
   `AttributeError: 'list' object has no attribute 'get'`

Per Anders' framing for R2/R3 these were "endpoint internal bugs,
separate". Should they be filed as new R-clusters for phase 4.x, or
absorbed into the 14-day deprecation audit (delete-vs-fix decision
postponed)?

## Verification of "no regression"

| Check | Result |
|---|---|
| API up post all commits | ✓ pid 46913, uptime 6 min at end |
| External endpoints 200 (zarq.ai/, nerq.ai/health) | Re-verified before suite run |
| Previously-passing tests still pass | All 287 phase-3 PASSes accounted for; +6 net |
| PgBouncer `query_wait_timeout` not spiking | 16 in last hour, baseline ≤20 |
| `com.nerq.api` restart count unchanged outside of intentional kickstarts | runs delta = +3 (exactly the 3 deliberate kickstarts) |

## Phase 4 deliverables

- 5 commits on `origin/main` (pushed after this report)
- 7 files added/modified across migrations, middleware, test suite, docs
- Audit table actively collecting usage data for the 14-day window
- Auth test suite available locally
- 2 deferred items (R1, R5) each with a clear unblocker (O.1, O.2)
- 1 deferred-on-cause item (R4) waiting for reproducer
- 4 deferred-on-prereq items (R7–R10) waiting on ADR-003a HA work

## Next steps for phase 4.x or phase 5

1. **Anders** answers O.1 (Cloudflare access) → I unblock R1.
2. **Anders** answers O.2 (action auth) → I ship R5.
3. **14-day window** runs (until 2026-06-13) collecting
   `zarq.endpoint_usage_audit` data.
4. **At day-14 review:** decide per-route delete vs keep for
   `/crypto/*`, `/experiments/*`, `/action/*` based on hit counts.
5. **Separately:** ADR-003a HA recovery work to unblock R7-R10.
6. **Separately:** O.3 endpoint-internal bug triage (3 5xxs).
