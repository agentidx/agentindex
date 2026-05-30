# ZARQ surface test suite

Permanent, reusable smoke + regression suite covering everything ZARQ
exposes (HTTP routes, MCP tools, HTML templates, Cloudflare-routed origins,
DB-level data freshness). Designed as input for the phase 3 root-cause
categorization but kept alive afterward as the regression net.

## Quick start

```bash
# localhost only — fast, after code changes
tests/zarq_surface/runners/smoke_localhost.sh

# production via Cloudflare — slow, periodic
tests/zarq_surface/runners/smoke_production.sh

# everything: both targets + DB freshness + MCP + cloudflared parity
tests/zarq_surface/runners/full_audit.sh
```

Outputs:
- pytest stdout: per-test pass/fail
- `docs/status/zarq_surface_test_run.json`: machine-readable summary
- `docs/status/zarq_test_failures_20260530/<test-id>.txt`: per-failure
  raw response excerpts so we can inspect after the fact

## How tests are structured

Each test file isolates a class of surface:

| File | Surface | Source of truth |
|---|---|---|
| `test_http_endpoints.py` | 200+ ZARQ-relevant FastAPI routes | grep against `agentindex/**.py` at session start (`route_discovery.py`) |
| `test_mcp_tools.py` | 19 MCP tools | static list aligned with `agentindex/crypto/zarq_mcp_server.py` |
| `test_templates_render.py` | 18 ZARQ Jinja templates | static list of canonical paths |
| `test_data_freshness.py` | zarq.* tables with cadence | freshness thresholds map in `conftest.py` |
| `test_cloudflared_routes.py` | hostname → origin parity | static canonical reference points |

All tests are parametrized over `target ∈ {localhost, production}` so we
can isolate Cloudflare/ingress issues from app-layer issues at the test
level. Override with `--zarq-target localhost` or `--zarq-target production`.

## Failure classification

Each failure gets one of these categories (see `conftest.FailureCategory`):

| Category | Meaning |
|---|---|
| `HTTP_5XX` | Server crash; immediate |
| `HTTP_4XX_unexpected` | 404 on a route that exists in code; 401/403 on a public path |
| `TIMEOUT` | Request took longer than 8s |
| `EMPTY_RESPONSE` | 200 with empty body / `{}` / list of zero |
| `STALE_DATA` | Latest DB timestamp older than the per-table threshold |
| `PARSE_ERROR` | Body not parsable as JSON when it should be |
| `EXCEPTION_IN_BODY` | Response contains a traceback or `Internal Server Error` marker |
| `DB_TABLE_MISSING` | 5xx + `relation "X" does not exist` in body |
| `DB_COLUMN_MISSING` | 5xx + `column "X" does not exist` in body |
| `CACHE_NOT_BUILT` | Body matches placeholder/cache-missing pattern |
| `WRITE_FAILED` | POST/PUT returned 200 but inserted row missing |
| `CLOUDFLARED_GAP` | Local origin returns expected status but production does not |
| `NETWORK_ERROR` | DNS failure, connection refused, TLS error |
| `SKIP_FLAKY` | Documented intermittent — escalates if the pattern persists |

## What this suite does NOT do

- Retry. The spec is explicit: an endpoint that fails once gets recorded
  as a fail, not retried to PASS.
- Auto-recovery. No restart-the-API, no clear-the-cache, no roll-the-pool.
  Pure measurement.
- Hint at root causes beyond the category label. Speculation belongs in
  phase 3.
- Modify the application or its data. The paper-trading write test is
  declared in `fixtures/synthetic_requests.json` but kept disabled until
  the schema for `is_test` isolation is verified.

## Updating the suite

Adding a new HTTP route? Nothing to update — `route_discovery.py` picks it
up automatically if the path or handler matches a ZARQ keyword.

Adding a new MCP tool? Append to `TOOL_CASES` in `test_mcp_tools.py`.

Adding a new template? Append to `TEMPLATE_CASES` in
`test_templates_render.py` with a canonical render path.

Adding a new zarq.* table with cadence? Update `freshness_thresholds` in
`conftest.py` AND the `_all_cases` list in `test_data_freshness.py`.

## Pre-flight rules

Before pushing a fix that touches anything the suite hits, run
`smoke_localhost.sh` and verify zero new failures vs the last known good
run (`docs/status/zarq_surface_test_run.json`). If the suite itself
generates failures during a regression hunt, it should be the LAST resort
the broken endpoint is taken out of rotation — not the first place a
hypothesis lives.

## Open work

See `docs/status/zarq_surface_inventory_20260530.md` section E for the
phase-2 test-scope decisions and `docs/tracking/pgbouncer-failover.md`
for related infra resilience work that determines whether the production
target stays reliably testable.
