# L1 observation — wave comparator

**Task:** T102 (L1 observation-expander: wave-aware 6h comparator).
**Script:** `scripts/observation_l1_canary.py`.
**Host:** `smedjan.nbg1.hetzner` (systemd unit `smedjan-l1-observation`).

## What the flag does

`scripts/observation_l1_canary.py --wave-comparator` adds one section to
the Markdown report:

```
## Wave comparator (6h run)

| Cohort                            | AI-bot crawls 7d | Citations 7d | 5xx 24h total | 5xx 24h count |
|-----------------------------------|-----------------:|-------------:|--------------:|--------------:|
| Wave 1 (gems+homebrew)            |              ... |          ... |           ... |           ... |
| Wave 2 (npm+pypi+crates)          |              ... |          ... |           ... |           ... |
| Wave 3 (remaining, N registries)  |              ... |          ... |           ... |           ... |
```

Wave 3 is resolved at runtime as *every enriched non-king registry not in
Wave 1 or Wave 2*, so it automatically absorbs new registries as they
finish enrichment. The section lists those registries underneath the
table so a glance is enough to see what Wave 3 currently covers.

Without the flag the script produces byte-identical output to its
pre-flag form (verified by diffing `render(baseline, obs)` against the
pre-edit version with fixed inputs).

## Slug → wave resolution

Some slugs are enriched in multiple registries (e.g. a package published
under both npm and pypi). The resolver assigns each seen slug to its
**lowest-numbered wave** — so traffic for a slug in both Wave 1 and Wave 2
is counted under Wave 1. This keeps Wave 1's AI-bot-crawls-7d aligned
with the existing `## Trend vs baseline` section, which itself prefers
gems/homebrew when disambiguating.

The resolver is also *seen-slug-first*: the analytics_mirror scan runs
first, collects unique /safe/<slug> slugs, and only then asks Nerq which
registries those slugs live in. This keeps the Postgres load bounded by
traffic (thousands of slugs) rather than by the enriched corpus
(~2.4M rows). An earlier implementation queried every enriched slug up
front and hit the Nerq RO statement timeout.

## Systemd — every-other-tick alternation

The `smedjan-l1-observation.timer` on smedjan fires every 12 h. The
service unit alternates `--wave-comparator` based on UTC-hour parity so
the flag passes on one out of every two ticks (24 h cadence), stateless:

```ini
ExecStart=/bin/sh -c 'if [ $(( $(date -u +%%H) / 12 )) -eq 0 ]; then \
  exec /usr/bin/python3 /home/smedjan/agentindex/scripts/observation_l1_canary.py --wave-comparator; \
else \
  exec /usr/bin/python3 /home/smedjan/agentindex/scripts/observation_l1_canary.py; \
fi'
```

The 12 h timer fires at two fixed UTC hours per day (currently 02:53 and
14:53). `hour/12` is 0 in the morning bucket and 1 in the afternoon
bucket — the morning tick gets the flag, the afternoon tick doesn't. If
the timer gets re-seeded (reboot, manual restart) the parity simply
follows the new fire times; no state file to manage.

Canonical copy of the unit lives at
`/etc/systemd/system/smedjan-l1-observation.service` on smedjan. The
timer file is unchanged from F5.

## Re-apply the systemd unit

If the unit gets reverted or reinstalled, the canonical body is:

```ini
[Unit]
Description=Smedjan L1 canary 12h observation snapshot (alternates --wave-comparator every other tick = 24h cadence)
After=network.target postgresql.service

[Service]
Type=oneshot
User=smedjan
Environment=PYTHONPATH=/home/smedjan/agentindex
Environment=SMEDJAN_CONFIG_DIR=/home/smedjan/smedjan/config
Environment=SMEDJAN_BASELINE_JSON=/home/smedjan/smedjan/baselines/L1-canary-gems-homebrew-PRE-2026-04-18.json
Environment=SMEDJAN_OBS_DIR=/home/smedjan/smedjan/observations
WorkingDirectory=/home/smedjan/agentindex
ExecStart=/bin/sh -c 'if [ $(( $(date -u +%%H) / 12 )) -eq 0 ]; then exec /usr/bin/python3 /home/smedjan/agentindex/scripts/observation_l1_canary.py --wave-comparator; else exec /usr/bin/python3 /home/smedjan/agentindex/scripts/observation_l1_canary.py; fi'
ExecStartPost=/usr/bin/python3 -m smedjan.scripts.emit_evidence
StandardOutput=append:/home/smedjan/smedjan/worker-logs/l1-observation.log
StandardError=append:/home/smedjan/smedjan/worker-logs/l1-observation.log
TimeoutStartSec=300
```

Apply with `sudo tee /etc/systemd/system/smedjan-l1-observation.service`,
then `sudo systemctl daemon-reload`.

## What this does NOT change

- `emit_evidence` still runs as `ExecStartPost` and still evaluates the
  same green criteria against the canary cohort. The Wave 2/3 rows in
  the pivot are informational — they do not gate any task. T001/T002
  evidence signals remain canary-anchored.
- The cumulative JSONL log (`L1-canary-observations.jsonl`) is unchanged —
  wave pivots are not written there. If we need historical wave trend
  data, a follow-up task should add a separate JSONL so the canary log
  stays byte-compatible with the existing consumers.
- The ntfy headline is unchanged (still reports canary 12h 5xx and
  citations). Wave summaries are in the Markdown report, not the push.

## Verification after deploy (2026-04-19)

- Manual trigger `sudo systemctl start smedjan-l1-observation.service`
  at 07:36 UTC (hour/12 == 0) wrote a report ending in a populated
  `## Wave comparator (6h run)` section. Runtime ~14 s including the
  emit_evidence ExecStartPost.
- Wave 1 AI-bot crawls 7d = 1,001 matches the canary's
  `## Trend vs baseline` line (gems 566 + homebrew 435 = 1,001), confirming
  the lowest-wave-wins slug resolver.
- Without the flag, `render(baseline, obs)` output is byte-identical to
  the pre-edit script given the same inputs (len 1,500 bytes in the
  fixture, both versions).
