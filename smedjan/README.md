# Smedjan Factory Core — Phase A

Autonomous task-queue runtime for Nerq / ZARQ. Phase A ships the
infrastructure; the worker is a stub that does NOT invoke `claude` until
Phase B activation (after the L1 canary 48h observation window closes on
2026-04-20 13:34 local).

## Module layout

| File | Purpose |
|---|---|
| `schema.sql` | Postgres DDL — `smedjan` schema, enum types, tasks / evidence_signals / worker_heartbeats tables, indexes. Applied to the Nbg primary at 100.119.193.70. Idempotent. |
| `config.py` | DSN, paths, ntfy topic, auto-yes whitelist, forbidden-path list. All environment-derivable. |
| `ntfy.py` | Free-tier `ntfy.sh` helpers. |
| `factory_core.py` | `claim_next_task` (FOR UPDATE SKIP LOCKED), `mark_done / _blocked / _needs_approval`, `approve`, `record_evidence`, `heartbeat`, `parse_task_result`. All SQL lives here. |
| `cli.py` | argparse entry — `smedjan queue add / list / show / approve / block / next / resolve / evidence / heartbeats`. |
| `worker.py` | Claim-loop stub. `--dry-run` (default) claims tasks but marks them `needs_approval`. Phase B flips the default. |
| `seeds.sql` | T001–T010 + T015–T017 seed tasks. Idempotent `ON CONFLICT DO NOTHING`. |

Shell wrapper: `~/agentindex/scripts/smedjan` runs `smedjan.cli` inside the venv.

## Task-queue model

```
┌────────┐   deps+evidence      ┌──────────┐  approve (risk=high     ┌─────────────┐
│pending │ ──────────────────▶ │needs     │ ──────────────────────▶ │approved     │
│        │                     │approval  │   requires --start-at)  │(optional   │
└────────┘                     └──────────┘                          │ start_at)   │
    │                               ▲                                └─────────────┘
    │ deps+evidence + auto-yes      │ resolve detects forbidden            │
    │                                │ whitelist → blocked                  │
    ▼                                │                                      │
┌────────┐                     ┌──────────┐                                │
│queued  │ ◀──────────────────│blocked   │                                │
└────────┘   block / unblock   └──────────┘                                │
    │                                                                       │
    │ worker claim (SKIP LOCKED)                                            │
    ▼                                                                       │
┌────────────┐  mark_done /             ┌────────┐                         │
│in_progress │ _blocked /               │done    │                         │
│            │ _needs_approval ───────▶ │blocked │ ◀───────────────────────┘
└────────────┘                          │needs_  │
                                        │approval│
                                        └────────┘
```

Auto-yes fires when **all** hold:

1. `risk_level = 'low'`
2. `whitelisted_files` is non-empty and every entry is under `AUTO_YES_WHITELIST_PREFIXES` in `config.py`
3. No entry overlaps `FORBIDDEN_PATHS`
4. All `dependencies` are `done`
5. `wait_for_evidence` (if set) has a matching row in `smedjan.evidence_signals`

Otherwise → `needs_approval` (or `blocked` if forbidden-path overlap).

## Worker structured-output contract

`claude` must end its output with one block:

```
---TASK_RESULT---
STATUS: done|blocked|needs_approval
OUTPUT_PATHS: comma,separated,paths
EVIDENCE: {"k": "v"}        # JSON; omit if nothing
NOTES: 1-3 sentence summary
---END_TASK_RESULT---
```

`factory_core.parse_task_result(stdout)` extracts this. No block → worker
marks the task `blocked`.

## Paid-API constraint

No paid APIs anywhere in the factory. Workers use the Max-subscription
`claude` CLI only. Data sources are free/subscription-included: GSC API,
Bing WMT API, IndexNow, OSV, OpenSSF Scorecard, Cargo/npm/PyPI registries,
manual CSV exports. See memory `feedback_no_paid_apis.md`.

## Activating Phase B (after 2026-04-20 13:34 local)

1. Anders reviews `smedjan-factory-v0`, merges to `main`.
2. Set ntfy-visible status signal:
   ```
   smedjan queue evidence l1_canary_observation_48h --payload '{"verdict":"green","5xx_48h":0}'
   smedjan queue resolve
   ```
   That promotes T001 from pending → needs_approval (high risk + scheduled_start_at required).
3. Rename the LaunchAgent:
   ```
   mv ~/Library/LaunchAgents/com.nerq.smedjan.worker.plist.disabled \
      ~/Library/LaunchAgents/com.nerq.smedjan.worker.plist
   launchctl load -w ~/Library/LaunchAgents/com.nerq.smedjan.worker.plist
   ```
4. Worker starts claiming. Watch ntfy and `smedjan queue heartbeats`.

## Operational bits

- Heartbeat table (`smedjan.worker_heartbeats`) updates every claim; a
  worker older than `WORKER_CLAIM_TTL_MINUTES` without a heartbeat means
  a dead process — re-claim logic is a Phase-B TODO.
- Session grouping (`session_group` column) is stored but not yet used —
  Phase B will batch `L2` tasks in a shared `claude` session.
- Fallback layers: `is_fallback=true` tasks (F1/F2/F3 categories) are
  claimed only when the primary queue is empty.
