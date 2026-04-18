# Evidence Signals Runbook

**Owner:** Smedjan factory core
**Purpose:** How observation-driven evidence signals unblock gated tasks.

---

## What is an evidence signal?

A row in `smedjan.evidence_signals` (Postgres schema `smedjan`, database
`smedjan` on the smedjan.nbg1 host). Any task whose `wait_for_evidence`
column matches an existing signal `name` is promoted out of `pending` by
`factory_core.resolve_ready_tasks()` the next time it runs.

Signals are written either by:

1. **Auto-emitter** — `smedjan.scripts.emit_evidence` evaluates green
   criteria against observation artefacts and inserts the row when all
   gates are met. This is the primary path.
2. **Manual override** — an operator forces a signal via the CLI:
   `smedjan queue evidence <name> --payload '{"forced":true}'`.

Both paths use the same upsert (`ON CONFLICT (name) DO UPDATE`), so it is
safe to run either repeatedly.

---

## Known signals

### `l1_canary_observation_48h`

**Gates task:** T001 (L1 Wave 2 rollout — npm/pypi/crates).
**T0:** `2026-04-18T11:34:18Z` (L1 canary deploy; hardcoded in
`emit_evidence.L1_CANARY_T0` until the schema grows a `deploys` table).
**Green criteria (all must hold):**

- `now - T0 >= 48h`.
- The observation JSONL (`~/smedjan/observations/L1-canary-observations.jsonl`)
  contains at least 4 entries whose `ts >= T0` (48h of 12h cadence).
- Every post-T0 entry has:
  - `status_5xx.{12h,24h}.{gems,homebrew}.5xx == 0`.
  - `whole_12h_5xx / whole_12h_total < 0.2%`.
- The most recent post-T0 entry shows non-zero canary-cohort /safe/*
  activity over 12h (`sum(status_5xx.12h.*.total) > 0`) — proves the
  pages are being exercised, not just silent.

**Payload written on green:**
```json
{"5xx_48h": 0, "observations": N, "canary_24h_hits": N,
 "canary_12h_hits": N, "t0": "...", "verdict": "green"}
```

### `l1_wave2_observation_48h`

**Gates task:** T002 (L1 Wave 3 rollout — all non-skip registries).
**T0:** `T001.scheduled_start_at` (or `done_at` if T001 was auto-claimed).
The emitter reads this live from `smedjan.tasks`; while T001 is not done,
the signal is skipped and logged as `T001 not yet done — wave2 T0 undefined`.
**Green criteria:** Identical to `l1_canary_observation_48h` but re-anchored
on the Wave-2 T0.

---

## Automatic emission

The `smedjan-l1-observation.service` systemd unit runs every 12h (via
`smedjan-l1-observation.timer`). Its `ExecStartPost` hook invokes the
emitter:

```ini
ExecStartPost=/usr/bin/python3 -m smedjan.scripts.emit_evidence
```

No additional scheduling is needed — every observation run is followed by
an evaluation pass. Failures in the emitter do **not** fail the
observation run (systemd logs both independently).

Logs land in `/home/smedjan/smedjan/worker-logs/l1-observation.log`. Filter
for `smedjan.emit_evidence:` to see per-signal verdicts.

---

## Manual dry-run

From any host with `PYTHONPATH=/home/smedjan/agentindex` and a valid
`SMEDJAN_CONFIG_DIR`:

```bash
SMEDJAN_CONFIG_DIR=/home/smedjan/smedjan/config \
    python3 -m smedjan.scripts.emit_evidence --dry-run
```

- `--dry-run` — evaluates only, never writes.
- `--signal l1_canary_observation_48h` — evaluate a single signal.
- `--verbose` — DEBUG logging.

Expected output while still inside the 48h window:

```
l1_canary_observation_48h NOT green: only 3.9h since T0 ...
l1_wave2_observation_48h  NOT green: T001 not yet done — wave2 T0 undefined; skipping
```

When green, the line flips to `... GREEN: all N windows clean; canary 24h hits=...`
and the row is upserted.

---

## Operator force-emit (urgent promotion)

If observation infrastructure is offline but you have other evidence that
a signal is safe to fire (e.g. whole-Nerq 5xx graphs on Grafana), you can
force-emit with a payload annotating why:

```bash
smedjan queue evidence l1_canary_observation_48h \
    --payload '{"forced": true, "operator": "anders",
                "reason": "jsonl corrupted; verified clean via Grafana",
                "verdict": "green-manual"}'
```

This writes a `created_by` of `$USER` (from the CLI) and runs the same
`resolve_ready_tasks()` sweep, so any pending gated task promotes
immediately. The forced row remains distinguishable from an auto-emitted
row by `payload.forced == true`.

**Use sparingly.** The whole point of evidence gates is to make
auto-promotion safe; a force-emit that turns out wrong will claim an
L1 high-risk task against a degraded system.

---

## Verifying the signal landed

```bash
PGPASSWORD=$SMEDJAN_APP_PW psql -h localhost -U smedjan_app -d smedjan \
    -c "SELECT name, available_at, created_by, payload
        FROM smedjan.evidence_signals ORDER BY available_at DESC;"
```

And check the task queue followed along:

```bash
smedjan queue list
```

T001 should now be `queued` or `needs_approval` (per risk gating) rather
than `pending`.

---

## Adding a new signal

1. Add an evaluator function returning a `Verdict` in
   `smedjan/scripts/emit_evidence.py`.
2. Register it in the `SIGNAL_SPECS` dict.
3. Seed the downstream gated task with
   `wait_for_evidence = '<new_name>'` in `smedjan/seeds.sql`.
4. Document the green criteria here. Include T0 source (hardcoded,
   derived from a task, or pulled from a config file).

---

*Last updated: 2026-04-18 (F5 rollout).*
