# ZARQ Surface Test Results — 2026-05-30

> **Phase 2 of the systematic ZARQ surface audit.** Test suite at
> `tests/zarq_surface/` executed against both `localhost` and `production`
> targets. This document is the per-failure factual record. **No fixes, no
> root-cause analysis** beyond the category label — that's phase 3.

**Suite version:** committed at the same time as this report.
**Run start:** 2026-05-30 10:14:43 CEST. **Run end:** 10:19:48 CEST. **Duration:** 5:03.
**Pre-flight at start:** `com.nerq.api pid=34176 runs=2144` (3 restarts since
the morning fix), PgBouncer 9 `query_wait_timeout` events since 10:00,
Nbg `:5432` accepting. Git tree clean.

## A) Top-level summary

| Metric | Count | % |
|---|---|---|
| Tests collected | 449 | 100.0% |
| PASS | 223 | 49.7% |
| FAIL | 226 | 50.3% |
| SKIP | 0 | 0.0% |
| Slow (>2s) | 19 | — |

**By failure category:**

| Category | Count |
|---|---|
| `HTTP_4XX_unexpected` | 211 |
| `TIMEOUT` | 5 |
| `EMPTY_RESPONSE` | 4 |
| `CLOUDFLARED_GAP` | 2 |
| `HTTP_5XX` | 2 |
| `PARSE_ERROR` | 1 |
| `NETWORK_ERROR` | 1 |

**By target:**

| Target | Failures |
|---|---|
| `localhost` | 105 |
| `production` | 118 |
| `pg-nbg` (freshness) | 1 |
| `diff` (cloudflared parity) | 2 |

**Response time per category** (avg / p99, ms):

| Category | Avg | p99 | n |
|---|---|---|---|
| PASS (slow only) | 4742 | 6483 | 19 |
| HTTP_4XX_unexpected | 180 | 2368 | 211 |
| EMPTY_RESPONSE | 36 | 7 | 4 |
| TIMEOUT | 8002 | 8002 | 5 |

Slowest passes (full list of >2s):

| Time | Endpoint | Target |
|---|---|---|
| 13684ms | `/kya` | production |
| 6483ms | `zarq_crypto_root` | diff |
| 6283ms | `/dashboard` | production |
| 6017ms | `/crash-watch` | production |
| 5522ms | `/crypto/signals` | production |
| 5185ms | `/learn` | production |
| 5116ms | `/compliance/mica` | production |
| 5071ms | `/admin/analytics-dashboard` | production |
| 5071ms | `/vitality/methodology` | production |
| 4684ms | `/insights` | production |

The `/kya` 13.7s exceeded the supposed 8s ceiling because the httpx client
treats the timeout per-redirect; the route follows redirects internally.
Recorded as PASS rather than TIMEOUT.

## B) Failures table (representative — full list in JSON)

Full machine-readable list at `docs/status/zarq_surface_test_run.json`.
Per-failure raw response excerpts at
`docs/status/zarq_test_failures_20260530/<test_id>.txt`. The table below
shows the most informative samples.

| # | Path | Category | Target | Status | Detail |
|---|---|---|---|---|---|
| 1 | `/rating/{token_id}` | `HTTP_4XX_unexpected` | localhost | 404 | route exists in `crypto_api.py:62`, returns 404 — likely prefix/include issue |
| 2 | `/ndd/{token_id}` | `HTTP_4XX_unexpected` | localhost | 404 | `crypto_api.py:114` |
| 3 | `/contagion/{token_id}` | `HTTP_4XX_unexpected` | localhost | 404 | `crypto_api_v3.py:119` |
| 4 | `/crash-thresholds/{token_id}` | `HTTP_4XX_unexpected` | localhost | 404 | `crypto_api_v3.py:232` |
| 5 | `/v1/agent/weekly` | `HTTP_5XX` | localhost | 500 | body: `Internal Server Error` |
| 6 | `/weekly` | `HTTP_5XX` | localhost | 500 | body: `Internal Server Error` |
| 7 | `/internal/reach` | `HTTP_4XX_unexpected` | both | 403 | `{"error":"unauthorized","hint":"add ?key=..."}` — known auth gate (suite bug, see D.3) |
| 8 | `/internal/yield` | `HTTP_4XX_unexpected` | localhost | 403 | same |
| 9 | `/internal/yield` | `NETWORK_ERROR` | production | — | route may not be exposed on the production hostname |
| 10 | `/v1/signal/feed` | `HTTP_4XX_unexpected` | production | 404 | works localhost (200), fails production |
| 11 | `/dashboard/data` | `TIMEOUT` | both | — | `client timeout after 8002ms`, both origins |
| 12 | `/citation-dashboard` | `TIMEOUT` | localhost | — | same |
| 13 | `/internal/yield` | `TIMEOUT` | production | — | timed out (route may exist but slow) |
| 14 | `/vitality` (canonical reference) | `CLOUDFLARED_GAP` | diff | — | local 200 in 930ms, prod TIMEOUT after 85988ms (89s) |
| 15 | `mcp/health` (canonical reference) | `CLOUDFLARED_GAP` | diff | 404 | local 200 in 4ms, prod 404 — mcp.zarq.ai/health doesn't route |
| 16 | `mcp/<every-tool>` | `HTTP_4XX_unexpected` | localhost | 406 | server response: `Not Acceptable: Client must accept text/event-stream…` (suite bug, see D.4) |
| 17 | `mcp/<every-tool>` | `HTTP_4XX_unexpected` | production | 404 | mcp.zarq.ai/mcp doesn't route to :8001/mcp via Cloudflare |
| 18 | `zarq_methodology.html` | `HTTP_4XX_unexpected` | both | 404 | `/crypto/methodology` 404 — actual route path may differ |
| 19 | `paper_trading.html` | `HTTP_4XX_unexpected` | both | 404 | `/crypto/paper-trading` 404 |
| 20 | `zarq.infrastructure_alerts` | `EMPTY_RESPONSE` | pg-nbg | — | `MAX(last_seen_at) IS NULL` — table empty because there are no current failures (this is actually a *PASS-shaped result* misclassified; see D.5) |

## C) Per-category groupings (input to phase 3)

The point of phase 2 was producing categories that phase 3 can root-cause
in batch. The groupings below identify the candidate batches.

### C.1 `HTTP_4XX_unexpected` (211 — 93% of all failures)

**Status-code breakdown:**

| Status | Count |
|---|---|
| 404 | 184 |
| 406 | 18 |
| 403 | 5 |
| 401 | 4 |

**Failures by source file** (the 404s, where each path is declared):

| Source file | Failures |
|---|---|
| `crypto_api_v3.py` | 32 |
| `crypto_agents_api.py` | 26 |
| `crypto_api_v2.py` | 16 |
| `crypto_api.py` | 12 |
| `yield_risk_api.py` | 10 |
| `experiments_api.py` | 10 |
| `crypto_seo_pages.py` | 8 |
| `dashboard.py` | 6 |
| `reach_dashboard.py` | 6 |
| `discovery.py` | 6 |
| `zarq_check_api.py` | 5 |
| `zarq_dashboard.py` | 4 |
| `signal_feed.py` | 4 |
| `weekly_signal.py` | 4 |
| `intelligence_api.py` | 3 |

Phase 3 candidate root cause: a small number of routers either aren't
included, are included conditionally with a guard that evaluates false at
runtime, or are included with a prefix that the decorator strings already
contain. The clustering by source file (32 in `crypto_api_v3.py`, 26 in
`crypto_agents_api.py`) strongly suggests batched fixes.

The 18 `406` are all MCP tool tests on localhost — see D.4 (suite bug).

The 5 `403` are all `/internal/*` paths — see D.3 (suite bug; these
require an API key).

The 4 `401` are auth-gated endpoints that are not part of the public
ZARQ surface; treat as suite scope issue.

### C.2 `TIMEOUT` (5)

| Path | Target |
|---|---|
| `/dashboard/data` | localhost |
| `/dashboard/data` | production |
| `/citation-dashboard` | localhost |
| `/internal/yield` | production |
| `/weekly` | production |

Phase 3 candidate root cause: these paths likely hit Postgres queries
that take >8s (consistent with this session's PgBouncer
`query_wait_timeout` observations on Nbg). `/dashboard/data` failing on
both targets points to the same upstream slowness regardless of ingress.

### C.3 `HTTP_5XX` (2)

| Path | Target | Status | Body |
|---|---|---|---|
| `/v1/agent/weekly` | localhost | 500 | `Internal Server Error` |
| `/weekly` | localhost | 500 | `Internal Server Error` |

Both come from `weekly_signal.py`. Production target hit different
errors (404 + NETWORK_ERROR) for the same paths — the routes may not
even be exposed on production hostnames.

### C.4 `EMPTY_RESPONSE` (4)

| Path | Target | Bytes |
|---|---|---|
| `zarq.infrastructure_alerts` | pg-nbg | NULL MAX |
| `/zarq2026indexnow.txt` | localhost | 16 |
| `/google{token}.html` | localhost | 44 |
| `/health` | localhost | 97 |

`/health` and the verification-marker files (`google*.html`,
`*indexnow.txt`) are *intentionally* small. Suite false positive — the
<200-byte HTML guard should exempt known-tiny endpoints. The
`zarq.infrastructure_alerts` "empty" is actually a healthy signal (no
open alerts right now), misclassified by the freshness test.

### C.5 `CLOUDFLARED_GAP` (2)

| Reference point | Local | Prod | Verdict |
|---|---|---|---|
| `/vitality` | 200 (930ms) | TIMEOUT (85988ms) | Cloudflare routes correctly but origin is slow on prod path |
| `mcp/health` | 200 (4ms) | 404 (250ms) | `mcp.zarq.ai/health` isn't reaching the :8001 backend's `/health` |

The `/vitality` 85s production timeout exceeds our suite's 8s
client-timeout — the httpx client kept the connection open across
Cloudflare-edge retries. This is the most striking single result of the
audit: the production path of `/vitality` is effectively dead under
default request behavior.

The MCP-health-404 confirms that `mcp.zarq.ai` ingress maps to a backend
that doesn't expose `/health`, or the host header isn't being passed
through correctly. (Localhost direct works.)

### C.6 `PARSE_ERROR` (1) + `NETWORK_ERROR` (1)

| Path | Target | Detail |
|---|---|---|
| One MCP call | production | JSON decode failure (response was probably a Cloudflare error page) |
| `/internal/yield` | production | ConnectError / DNS / TLS issue |

## D) Cloudflared-vs-localhost diff

Paths where the localhost and production targets returned *materially
different* outcomes (status codes; ignoring same-error-different-elapsed):

| Path | Local | Prod | Implication |
|---|---|---|---|
| `/v1/signal/feed` | 200 | 404 | exposed locally, not via prod hostname (or different prefix) |
| `/internal/yield` | 403 | NETWORK | route exists locally with auth gate, fails to even connect prod-side |
| `/v1/agent/weekly` | 500 | 404 | locally crashes; prod hostname doesn't route it |
| `/weekly` | 500 | NETWORK | same |
| `/vitality` (canonical) | 200 | 85s timeout | Cloudflare reaches origin but origin is slow only over prod path |
| `mcp.zarq.ai/<anything>` | 406 | 404 | local MCP server returns 406 (suite-bug for Accept header), production maps `mcp.zarq.ai/mcp` to a path that 404s |

The full set of MCP-tool entries shows the same `406 (local) / 404 (prod)`
shape for all 19 tools — one batched root cause both sides.

## E) Raw response dumps

Every failed test wrote `docs/status/zarq_test_failures_20260530/<test_id>.txt`
with the response body excerpt, status, elapsed, and category. Inspect
without re-running:

```bash
ls docs/status/zarq_test_failures_20260530/ | head
cat docs/status/zarq_test_failures_20260530/<test_id>.txt
```

## F) Top 5 root-cause *candidates* for phase 3

Observation-level only — no analysis.

1. **One or more router-include calls don't take effect for the crypto API
   family.** 86 of the 184 `404`s come from
   `crypto_api_v3.py` (32), `crypto_agents_api.py` (26), `crypto_api_v2.py`
   (16), `crypto_api.py` (12). These are top-of-list candidate batches.

2. **MCP server's `/mcp` endpoint is misrouted on production.** All 19
   tools return `404` on `mcp.zarq.ai/mcp`. Localhost direct works in
   structure (but our suite sends the wrong Accept header — see D.4).

3. **`/dashboard/data` and `/citation-dashboard` time out on both targets.**
   Persistent 8s+ Postgres queries — consistent with the PgBouncer
   saturation observed all morning.

4. **`/vitality` production path takes 85+ seconds.** Same Cloudflare
   tunnel, same backend, but the production-side route is dramatically
   slower than localhost — distinct enough to be its own root cause.

5. **Two weekly endpoints (`/weekly`, `/v1/agent/weekly`) return 500.**
   Localhost-confirmed bug in `weekly_signal.py`. Not blocked on routing.

## G) Suite-quality notes (not failures of ZARQ; failures of the suite)

These are recorded so phase 3 doesn't waste time on them.

- **D.3 — `/internal/*` 403s.** Three routes (`/internal/reach`,
  `/internal/reach.json`, `/internal/yield`) require an API key. They're
  not part of the public ZARQ surface; suite scope should exclude them
  going forward.
- **D.4 — MCP localhost 406.** The server requires `Accept: text/event-stream`
  for the MCP transport. Our test sends `Content-Type: application/json`
  only. Suite refinement: add the Accept header. Then the 19 localhost
  MCP failures should change category; the production 404s will still
  show up as real bugs.
- **D.5 — `zarq.infrastructure_alerts` empty.** A *no open alerts* state
  is healthy. The freshness test treats empty MAX as a failure; for this
  table specifically, MAX-IS-NULL should be PASS.
- **`/health`, `/zarq2026indexnow.txt`, `/google*.html` flagged
  EMPTY_RESPONSE.** These return small bodies by design; the <200-byte
  guard needs an allowlist.
- **`/kya` 13.7s under "PASS" instead of TIMEOUT.** httpx
  `follow_redirects=True` resets the timeout per redirect; total elapsed
  isn't bounded. Suite refinement: switch to `Timeout(connect=4, read=8)`
  and `follow_redirects=False` plus an explicit redirect-chain test.

These 5 suite-quality items would, once fixed, reduce the failure count by
roughly 24 (19 MCP-localhost + 3 `/internal` + 1 freshness + a handful of
small-body false positives). Real failure count stabilizes around ~200,
still dominated by `HTTP_4XX_unexpected` 404s.

## Out-of-scope for phase 2

- Fixing any of the failures.
- Speculating about *why* `crypto_api_v3.py` routes 404 (phase 3).
- Refactoring the suite to fix D.3–D.5 (each is a one-line change; will be
  bundled with phase 3 work or a separate suite-polish commit later).
- Adding paper-trading write-side tests. Disabled in
  `fixtures/synthetic_requests.json` until the schema for `is_test`
  isolation is verified.
