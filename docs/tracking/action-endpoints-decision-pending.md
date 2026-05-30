# Tracking: `/action/{approve,reject,dismiss}` — audit-driven decision

**Opened:** 2026-05-30 (phase 4 R5 deferral)
**Status:** Open. Decision deferred until 2026-06-13.
**Owner:** Anders (decides at day-14 review)

## Current state

The three endpoints live in `agentindex/dashboard.py:10-30`:

```python
@app.get("/action/approve")  # ?id=...
@app.get("/action/reject")   # ?id=...
@app.get("/action/dismiss")  # ?id=...
```

Each calls into `agentindex.agents.action_queue.{approve_action, reject_action, mark_dismissed}`
and returns an HTML redirect. They are **writes** — mutate the action
queue.

They are **not** mounted in `agentindex/api/discovery.py`. Every external
request to `/action/*` returns 404.

## Why this is deferred

Phase-3 plan F.3 and Anders' answer: "behåll som live admin-yta +
deprecation_logger". Phase-3 risk register: "gate first, mount second"
(write endpoints without auth = real exposure risk).

Phase-4 surfaced the gap: there is no shared "admin auth" pattern in the
codebase. `/internal/*` uses `NERQ_DASHBOARD_KEY` for **reads only**.
`/zarq/dashboard*` uses `ZARQ_METRICS_TOKEN` also for reads. There is no
established **write-action** auth scheme. Inventing one without evidence
that the endpoints are actively used is premature.

So instead: keep them at 404 for the 14-day window, let
`DeprecationLoggerMiddleware` (commit `2f47d3e`) record any hits, then
decide at day-14 based on **who is hitting them**.

## Audit-data start

`DeprecationLoggerMiddleware` mounted in commit `2f47d3e` (2026-05-30
11:42 CEST). All requests to `/action/*` are logged to
`zarq.endpoint_usage_audit`, even though the route returns 404.

**Day-14 review date: 2026-06-13.**

## Decision criteria

At day-14, run:

```sql
SELECT
  client_ip,
  COUNT(*) AS hits,
  MIN(called_at) AS first_seen,
  MAX(called_at) AS last_seen,
  array_agg(DISTINCT endpoint) AS paths
FROM zarq.endpoint_usage_audit
WHERE endpoint LIKE '/action/%'
  AND called_at > '2026-05-30 11:42:00+02'
GROUP BY client_ip
ORDER BY hits DESC;
```

Interpret:

| Pattern | Decision |
|---|---|
| Only `127.0.0.1` / `100.64.0.0/10` (Tailscale) hits, no external | Delete the file. Nothing relies on it. |
| External hits from a small set of known operator IPs | Mount **behind an auth gate** — choose the gate based on the IP set. |
| External hits from many unknown IPs | Worrying — was the previous deployment somehow public? Investigate before mounting. **Do not mount.** |
| Zero hits at all | Delete the file. |

## What the fix looks like in the "mount with auth" case

If we proceed to mount, the auth gate should be the **same scheme** as
the rest of the operator surface — i.e. `NERQ_DASHBOARD_KEY` via
`?key=...`. Implementation:

1. Convert `dashboard.py`'s `app = FastAPI()` into a
   `router = APIRouter(prefix="/action", tags=["action"])`.
2. Add a per-handler `key: str = Query(...)` parameter with the same
   401 response shape as `reach_dashboard.py:175`.
3. Include the router in `discovery.py`, in the same neighborhood as the
   crypto_api / experiments_api includes (commits `abc7fa1` / `84a1472`).
4. The existing `DeprecationLoggerMiddleware` continues to capture usage.

## What the fix looks like in the "delete" case

1. Delete `agentindex/dashboard.py` (4 routes, all `/action/*` + `/`).
2. Verify no other module imports from it (`grep "from agentindex.dashboard"`
   should return zero hits).
3. Remove the `/action/` prefix from
   `DeprecationLoggerMiddleware`'s configured set in `discovery.py`.
4. Commit.

## Related

- Audit infrastructure: commit `2f47d3e` (PREP-1).
- Phase-3 F.3 answer + risk register: `docs/status/zarq_root_cause_plan_20260530.md`
- Phase-4 execution report: `docs/status/zarq_phase4_execution_20260530.md`
  section "R5 — deferred (auth-gate decision needed)".
