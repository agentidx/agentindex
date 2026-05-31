# Tracking: Crypto pipeline success canary

**Status:** proposed (not implemented)
**Surfaced by:** 2026-05-31 incident diagnosis
**Priority:** medium (after R-PIPE-1/2/3 resolved)

## Gap

The `com.nerq.crypto-daily` LaunchAgent runs at 04:00 CET daily. Its
exit code goes to the LaunchAgent's `LastExitStatus` (currently 256 =
failure). Nothing alerts on this.

The Smedjan smoke canary (`com.zarq.smedjan-canary`, 03:30 daily) only
watches the Smedjan daily-merge smoke test (boot-path health). It does
**not** read `zarq.crypto_pipeline_runs` and will not alert if the
crypto pipeline silently fails.

Today's discovery: the crypto pipeline has failed for the last 2 runs
(2026-05-30 04:00, 2026-05-31 04:00). The most recent successful entry
in `zarq.crypto_pipeline_runs` is id=374, run_date=2026-05-29. The data
in `zarq.nerq_risk_signals` is from 2026-05-29 22:40 — 36+ hours stale.
We discovered this only because we tried to manually rerun the pipeline
today.

## Implementation sketch

`scripts/pipeline_success_canary.py`:

```python
# Pseudocode
psql to agentindex_write:
  SELECT MAX(run_date) AS last_date, status, total_seconds
  FROM zarq.crypto_pipeline_runs
  WHERE status = 'OK'
  ORDER BY id DESC LIMIT 1;

today = date.today()
if last_date is None or last_date < today - timedelta(days=1):
    alert(host="100.119.193.70", port=5432,
          service="crypto-pipeline|STALE",
          severity="critical",
          error_msg=f"last OK run: {last_date} (>{days_late}d ago)")
```

LaunchAgent: `com.zarq.pipeline-canary.plist`
- StartCalendarInterval: 06:00 CET (2 hours after pipeline's 04:00 start)
- Runs `scripts/pipeline_success_canary.py`
- Writes to `zarq.infrastructure_alerts` via same pattern as Smedjan
  canary

## Alert resolution

The canary should also clear (UPDATE `resolved_at`) when a new OK run
appears for today. Same row-update pattern as `infra_healthcheck.py`.

## Why this matters

Same logic as the Smedjan-smoke gap that caused 2026-05-31's incident
to be discovered 5+ hours after onset rather than seconds. The pattern
is: silent automation + no read-back of the result = unbounded staleness.

The cost of implementing this is ~1 hour. The cost of not implementing
it is repeated late discovery of stale pipeline data.

## Out of scope

- Per-step canaries (which step failed, etc.) — start with binary "did
  the pipeline produce a fresh OK row today" and add granularity later.
- Re-running the pipeline automatically — recovery is human-driven for
  now.

## Links

- Smedjan smoke canary: `scripts/smedjan_smoke_canary.py`
  (commit `40c5802`)
- Today's incident report: `docs/incidents/20260531/incident_report.md`
- Pipeline diagnosis: `docs/status/pipeline_diagnosis_20260531.md`
