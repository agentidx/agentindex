# Phase B activation — worker go-live

**Scheduled decision point:** 2026-04-20 13:34 Europe/Stockholm (the
moment the L1 canary 48h observation window closes, assuming green
signals). Two placement plans exist; pick one on that day.

## Primary plan — worker on smedjan.nbg1.hetzner

**Prerequisite:** Claude Code CLI has shipped a viable headless Linux
auth (device-code flow, or static token export, or equivalent). See
`claude-code-linux-auth.md` for the retry signal.

Steps:

```bash
# 1. Update Claude Code on smedjan to the latest and verify the new flow
ssh smedjan 'claude update && claude auth --help'

# 2. Walk through auth per the new docs. After success:
ssh smedjan 'claude -p "hello, respond with a short sentence"'
# must return text without any TTY / browser intervention

# 3. Record green evidence, promote T001
smedjan queue evidence l1_canary_observation_48h \
    --payload '{"verdict":"green","5xx_48h":0,"citations_vs_baseline":"≥"}'
smedjan queue resolve     # promotes T001 pending → needs_approval

# 4. Install + load the Linux worker unit
ssh smedjan 'sudo bash -c "
cat > /etc/systemd/system/smedjan-worker.service <<UNIT
[Unit]
Description=Smedjan factory worker
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=smedjan
Environment=PYTHONPATH=/home/smedjan/agentindex
Environment=SMEDJAN_CONFIG_DIR=/home/smedjan/smedjan/config
Environment=SMEDJAN_WORKER_DRY_RUN=0
WorkingDirectory=/home/smedjan/agentindex
ExecStart=/usr/bin/python3 -m smedjan.worker --live
Restart=on-failure
RestartSec=30s
StandardOutput=append:/home/smedjan/smedjan/worker-logs/worker.log
StandardError=append:/home/smedjan/smedjan/worker-logs/worker.log
UNIT
systemctl daemon-reload
systemctl enable --now smedjan-worker.service
"'

# 5. Confirm Mac Studio disabled-plist stays disabled
launchctl list | grep com.nerq.smedjan.worker   # must return nothing
```

## Alternative plan — worker on Mac Studio (default choice if primary blocked)

**Use if** the primary plan is still blocked on Claude Code Linux auth
on 2026-04-20 13:34. This is the hybrid-architecture fall-back that
was in place during M1–M18 build.

Steps:

```bash
# 1. Record green evidence, promote T001 (same as primary)
smedjan queue evidence l1_canary_observation_48h \
    --payload '{"verdict":"green","5xx_48h":0,"citations_vs_baseline":"≥"}'
smedjan queue resolve

# 2. Rename the disabled LaunchAgent and load it on Mac Studio
mv ~/Library/LaunchAgents/com.nerq.smedjan.worker.plist.disabled \
   ~/Library/LaunchAgents/com.nerq.smedjan.worker.plist
launchctl load -w ~/Library/LaunchAgents/com.nerq.smedjan.worker.plist
launchctl list | grep smedjan.worker    # must show label + PID

# 3. Confirm smedjan-side unit (if ever created as dormant) stays down
ssh smedjan 'systemctl is-enabled smedjan-worker.service 2>&1'
# expected: "Failed to get unit file state ... No such file or directory"
```

The LaunchAgent at `smedjan/com.nerq.smedjan.worker.plist.disabled`
already points `SMEDJAN_WORKER_DRY_RUN=0` — renaming is sufficient.

### Why this is a safe second-best

The worker's job is to pull tasks from the smedjan DB on Hetzner,
invoke `claude` CLI, and push results back. Nothing about the
task-execution contract requires the worker to be co-located with the
DB; the smedjan DB is reachable over Tailscale from anywhere.

The only operational cost of keeping worker on Mac Studio:

- Nerq migration later requires moving the worker twice (Mac Studio →
  new Nerq host → smedjan once Linux auth unblocks). Small cost; the
  unit file is 40 lines either way.
- Mac Studio carries both roles (worker + canary_monitor +
  analytics-export). It handled that today without issue — CPU/RAM
  headroom is sufficient.

## Migration primary ↔ alternative

When Claude Code ships Linux auth and we move the worker from Mac Studio
to smedjan:

```bash
# 1. Authenticate on smedjan per the new flow (one-time)
ssh smedjan 'claude setup-token …'

# 2. Quiesce the Mac Studio worker
launchctl unload -w ~/Library/LaunchAgents/com.nerq.smedjan.worker.plist
mv ~/Library/LaunchAgents/com.nerq.smedjan.worker.plist{,.disabled}

# 3. Install + load the Linux systemd unit from primary plan step 4.
```

Any task that was in_progress at unload time stays `in_progress` in the
DB; the next worker (on smedjan) re-claims it via the reclaim logic
(Phase-B TODO tracked in `smedjan/README.md`).

## Green-signal definition for the 48h gate

"L1 canary observation 48h window closes green" means:

- `l1_observation` reports for the 48h window (4 consecutive runs by
  the 12h timer) show **zero 5xx** on the canary cohort
- whole-site 5xx rate stays under 0.2% over any 30-min window
- `canary_monitor` ntfy noise confined to already-known signals (e.g.
  the write_rate alert being investigated in T018) — no new categories

If any of those fail, Phase B is deferred and the trigger is the first
12h report after the affected signal goes back to green.

## Post-activation smoke

After either plan, verify:

```bash
# Inside 60s of worker starting, you should see a heartbeat
smedjan queue heartbeats

# Worker should mark T001 needs_approval (or complete it if Anders
# pre-approves with --start-at). Either way, it should not crash.
smedjan queue show T001
tail -f ~/smedjan/worker-logs/$(date +%Y-%m-%d).log     # (Mac Studio)
# or on smedjan:
#   ssh smedjan 'journalctl -u smedjan-worker.service -f'
```

First expected ntfy after activation: `[SMEDJAN] worker started`.
