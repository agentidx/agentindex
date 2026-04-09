# Session Handoff — 2026-04-09 Evening

**Previous session:** Claude chat, full day 2026-04-09 (~8 hours)
**Next session tasks:** Phase 0 Day 1 — Hetzner Nürnberg provisioning + open decisions from ADR-003 addendum

---

## Read first, in order

1. `CLAUDE.md` (repo root) — orientation, three-entity system, ground rules
2. `docs/buzz-context.md` — Buzz details, what she is, how to interact
3. `docs/adr/ADR-003-cloud-native-expansion-first.md` — active architecture strategy
4. `docs/adr/ADR-003-addendum-baseline-discoveries.md` — this morning's decisions, plus things baseline capture revealed that need Phase 0 decisions
5. `docs/strategy/phase-0-cloud-migration-plan.md` — implementation plan, this is what you execute from

Do not skip steps 1-4. The previous session invested real time in producing these documents specifically so you don't have to rediscover context.

---

## What got done today (2026-04-09)

This was a strategically heavy day. Seven major deliverables:

1. **ADR-003 written and committed** (`6448583` on main)
   - Cloud-native architecture
   - 2× Hetzner CPX41 (Nbg + Hel) + 1× CPX21 worker
   - Self-hosted Postgres with async streaming replication
   - Mac Studio + Mac Mini demoted to optional accelerators
   - Four-tier freshness SLA
   - Render-on-demand, not pre-render
   - Budget $75-85/month flat, cap at $100

2. **Phase 0 implementation plan written and committed** (same commit)
   - Phase 0: Cloud migration (2 weeks)
   - Phase 1: Parameterize Norwegian language model (3-5 days)
   - Phase 2: 50-language sprint (5-10 days)
   - Phase 3: Vertical pipeline (3-5 days)
   - Phase 4: 100-vertical sprint (2-3 weeks)
   - Total: 5-8 weeks from 2026-04-09 to "100 verticals × 50 languages live with freshness SLA"

3. **CLAUDE.md updated** so future sessions see ADR-003 as active
   - ADR-001 remains deferred
   - ADR-002 marked partially superseded in DR tier ordering

4. **OPERATIONSPLAN.md rewritten** for Buzz, installed at `~/.openclaw/workspace/OPERATIONSPLAN.md`
   - Backup saved as `OPERATIONSPLAN.md.bak-2026-04-09`
   - North Star changed from "AI Citation Rate 0/21 (feb 2026)" to monetization trigger
   - Added three-entity-system awareness, freshness SLA, autoheal rules update, known broken things
   - Temporary file-based reports channel (`~/.openclaw/workspace/reports/`) because Discord is broken
   - Buzz has NOT been restarted — next cron cycle will pick up the new plan naturally

5. **Baseline capture** at `~/nerq-baselines/2026-04-09-pre-migration/`
   - system.txt, postgres.txt, sqlite.txt, processes.txt, traffic.txt
   - configs/ with 4 critical config file copies
   - sacred/ with 10 HTML snapshots for byte-drift comparison
   - launchagents-inventory.md and launchagents-summary.txt

6. **Accounts ready for Phase 0 Day 1:**
   - Hetzner: project "nerq", ID **14112820**, SSH key `mac-studio-anders` as default, payment method inlagd
   - Backblaze B2: account active, **EU Central** region, B2 enabled, payment inlagd
   - Note: B2 phone verification is locked until after first billing cycle (policy, not a blocker)
   - Cloudflare Workers Paid: active but no longer needed (see pending decisions)

7. **ADR-003 addendum committed** documenting baseline discoveries that change Phase 0 execution

---

## Current system state (as of end of session)

- **Working tree:** presumed clean (verify with `cd ~/agentindex && git status` before starting work)
- **HEAD:** 6448583 plus the addendum commit if it's been pushed (verify)
- **Production:** Mac Studio still serving everything, no changes to production
- **Buzz:** running on Mac Studio, next health check should read new OPERATIONSPLAN.md
- **Postgres replication:** Mac Studio → Mac Mini still live (confirmed by baseline — `walsender` to `100.115.230.106`)
- **No Hetzner servers provisioned yet** — that's Phase 0 Day 1's job
- **Expansion:** paused for 2 weeks per ADR-003. Hidden registry fixes and language additions can continue in parallel on Mac Studio but nobody should be adding new verticals during cloud migration

---

## Phase 0 Day 1 — what to do in the next session

### Pre-flight checks (30 minutes)

1. Verify git is clean and latest: `cd ~/agentindex && git pull && git log --oneline -5`
2. Verify Buzz is running and read OPERATIONSPLAN.md is the new version: `head -20 ~/.openclaw/workspace/OPERATIONSPLAN.md` should show "Senast uppdaterad: 2026-04-09"
3. Verify reports/ directory exists: `ls -la ~/.openclaw/workspace/reports/`
4. Check if Buzz has written any reports to `~/.openclaw/workspace/reports/` since the previous session — if yes, read them
5. Verify baseline is still intact: `ls -la ~/nerq-baselines/2026-04-09-pre-migration/`

### Decisions that must be made with Anders before Day 1 execution

Per ADR-003 addendum, four open decisions:

1. **ZARQ migration strategy.** ZARQ runs on SQLite (`crypto_trust.db`, 1.1 GB). Options:
   - A. Migrate to Postgres before cutover (1-2 days extra, cleanest)
   - B. Litestream/rsync replication of SQLite (fastest, brittle)
   - C. Dual-deploy, ZARQ stays on Mac Studio initially
   
   Tentative preference: A. Discuss with Anders on Day 1.

2. **Ollama dependency.** `homebrew.mxcl.ollama` is running. Unknown consumer. Day 1 investigation: grep codebase for ollama/localhost:11434 references. If only Buzz uses it, decide: (a) migrate to API calls, (b) keep on Mac Studio as accelerator dependency.

3. **Cloudflare Workers Paid.** Not needed for ADR-003. Anders said in previous session he's open to downgrading. Tentative preference: downgrade to Free to save $5/month pre-revenue. Confirm with Anders.

4. **`agent_jurisdiction_status` table.** 57 GB, 64% of the Postgres database. Transfer will take 8-14 hours via Tailscale. Options:
   - A. Transfer as-is overnight
   - B. Trim before transfer
   - C. Schema refactor (post-Phase 0)
   
   Tentative preference: A for Phase 0, C flagged as follow-up.

### Hetzner Nürnberg provisioning (Day 1 execution, 2-3 hours)

Only after the 4 decisions above are made:

1. Go to Hetzner Cloud Console, project 14112820
2. Create a new server:
   - Location: **Nürnberg (nbg1)**
   - Image: **Ubuntu 24.04 LTS**
   - Type: **CPX41** (8 vCPU AMD, 16 GB RAM, 240 GB NVMe disk)
   - Network: default
   - SSH Keys: `mac-studio-anders` (should be default-selected)
   - Name: `nerq-nbg-1`
   - Labels: `env=production`, `role=primary`, `project=nerq`
   - Backups: enabled (~€3/month, worth it for the peace of mind during migration)
3. After provisioning, note the public IPv4 address
4. SSH in as root (using the SSH key): `ssh root@<ipv4>`
5. Run the hardening script that Claude writes in-session (Claude should write it fresh based on current Ubuntu 24.04 best practices)
6. Install: Tailscale, Postgres 16, Redis, Python 3.12, firewall (ufw), fail2ban, automatic security updates
7. Join Tailscale: `sudo tailscale up` with appropriate flags
8. Verify Mac Studio can reach it via Tailscale: `ping <tailscale-ip>` from Mac Studio
9. Commit server metadata (IPs, hostname, creation date) to a new file `docs/infrastructure/hetzner-inventory.md`

### What NOT to do in Day 1

- Do not touch production on Mac Studio. Everything remains running as today.
- Do not start Postgres replication yet. That's Day 3-4 after Mac Studio Postgres is prepared.
- Do not provision Helsinki yet. That's Day 6-7.
- Do not provision CPX21 yet. That's Day 2 or 3.
- Do not attempt ZARQ migration yet. That decision must be made first.

---

## Open questions carried from today

These are things the previous session discussed with Anders but did not finalize, and they may come up naturally in the next session:

1. **Does Buzz actually call `system_autoheal.py`?** We committed fixes on 2026-04-09 morning (`553a468`, `18bbe80`) but never verified they're in the active code path. The way to check: read a recent Buzz session in `~/.openclaw/agents/main/sessions/` and look for shell commands that invoke that script.

2. **Is the 06-08 UTC "traffic dip" really caused by autoheal restart loops?** The hypothesis is strong but not confirmed. With autoheal fixes now in place, observe the flywheel dashboard over the next few days — if the dip disappears, hypothesis confirmed.

3. **Discord integration remains broken.** Temp fix (file-based reports) is documented in OPERATIONSPLAN.md. Fixing Discord properly is a separate 30-60 min task that can happen any time.

4. **Two cloudflared processes running** — one legitimate (`com.cloudflare.cloudflared`), one apparently dead (`homebrew.mxcl.cloudflared` without arguments). Both go away at cutover anyway but it's a symptom of accumulated operational debt.

---

## Guiding principles (do not forget)

- **Welcome all traffic.** Default is always "let them in." This includes Meta crawlers, which are explicitly allowed per 2026-04-09 decisions.
- **Expansion-first.** 50 languages + 100 verticals before monetization. Trigger is 150K human visits/day × 7 days sustained. Current traffic is 10K-43K/day — we are **not** at trigger yet.
- **Three-entity system.** Anders + Buzz + Claude. Buzz is a colleague, not a system component. Read `docs/buzz-context.md` before operational work.
- **Not a coder.** Anders will not debug code. Do it yourself or explain clearly what you need verified.
- **Shell in heredoc.** Prefer Python for anything with markdown or special characters. Base64 for anything that needs to survive zsh+bash+markdown round-trips.
- **Commit often, push every time.** CI is on every push. Failed CI blocks the next step.
- **Ask before assuming.** Five minutes of clarification is cheaper than one hour of wrong execution.
- **Don't fight Buzz.** If you see processes starting/stopping that you didn't start, check if Buzz is doing something per OPERATIONSPLAN.md before assuming it's a bug.

---

## Files committed today (reference)

- `docs/adr/ADR-003-cloud-native-expansion-first.md` — architecture decision
- `docs/adr/ADR-003-addendum-baseline-discoveries.md` — this morning's baseline-driven adjustments
- `docs/strategy/phase-0-cloud-migration-plan.md` — 5-8 week implementation plan
- `docs/session-handoff-2026-04-09-evening.md` — this file
- `CLAUDE.md` — updated so future sessions find ADR-003 as active strategy

Plus, **on Mac Studio (not in repo):**

- `~/.openclaw/workspace/OPERATIONSPLAN.md` — new Buzz operations plan (backup at `.bak-2026-04-09`)
- `~/.openclaw/workspace/reports/` — temp reports directory
- `~/nerq-baselines/2026-04-09-pre-migration/` — full baseline capture

---

## Session ended cleanly

No production changes. No uncommitted work (assuming the addendum commit gets pushed before session ends). No open incident. System stable. Mac Studio serving as normal.

The previous session is satisfied with progress and recognizes that starting a new session with fresh context is better than continuing with a saturated one. Hetzner provisioning deserves a clear head.

Good luck.
