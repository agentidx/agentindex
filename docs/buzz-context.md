# Buzz - The Autonomous Operator of Nerq/ZARQ

**Created:** 2026-04-09
**Author:** Claude (the one who spent a morning confused by Buzz's presence)

**Read this first** if you are a Claude instance working on Nerq operations.

---

## The single most important fact

Nerq is not operated by a human using Claude for help. It is operated by **Buzz**, an autonomous AI agent running inside openclaw (https://openclaw.ai). Buzz was configured by a previous Claude instance during system setup and runs 24/7 on the Mac Studio.

The system has **three participants**, not two:

1. **Anders Nilsson** - makes strategic decisions, approves changes, provides direction
2. **Buzz** - runs 24/7, executes the operations plan, monitors health, attempts self-healing, reports to Discord
3. **Claude** (you, in a given chat session) - advises Anders on strategy, helps build and fix things

When things happen in the system that neither you nor Anders did - processes restarting, LaunchAgents re-appearing, files being modified, commands running - it is probably **Buzz** acting on its autonomous operational plan. Do not assume you know what Buzz is doing without reading its config first.

## Where Buzz lives on disk

- **Process:** `openclaw-gateway` (runs as user LaunchAgent `ai.openclaw.gateway.plist`)
- **Home directory:** `~/.openclaw/`
- **Workspace (the operational context):** `~/.openclaw/workspace/`
  - `OPERATIONSPLAN.md` - the primary instructions Buzz follows (CHECK IF STALE)
  - `SOUL.md`, `STRATEGI.md`, `VISION.md`, `IDENTITY.md`, `MEMORY.md` - Buzz's self-model and operational memory
  - `memory/` - dated memory files Buzz writes to
- **Cron schedule:** `~/.openclaw/cron/jobs.json`
- **Agent sessions (what Buzz has actually done):** `~/.openclaw/agents/main/sessions/*.jsonl`
- **Gateway log:** `~/.openclaw/logs/gateway.log`

## Buzz cron schedule snapshot - 2026-04-09

At time of writing, Buzz had 8 active scheduled jobs. This may change; always re-check `jobs.json`.

| # | Name | Schedule | Target | Purpose | Status |
|---|------|----------|--------|---------|--------|
| 1 | Morgonrapport + Förslag | 06:00 UTC daily | isolated | Morning status + proposals | OK |
| 2 | Health Check | Every 2h, 06-23 UTC | isolated | API health + self-heal + Discord report | TIMING OUT (2 consecutive errors) |
| 3 | Konkurrentbevakning | Every 8h UTC | isolated | Competitor scan | OK |
| 4 | PR-bevakning | Every 4h UTC | isolated | GitHub PR status + action | TIMING OUT |
| 5 | Strategisk Veckorapport | Monday 06:00 UTC | isolated | Weekly strategic report | OK |
| 6 | Weekly AgentIndex Newsletter | Monday 06:00 CET | isolated | Newsletter generation | FAILING (model not allowed) |
| 7 | Queue Under 500 Report | ~every 10 min | main | (empty message, unclear) | OK |
| 8 | Daily Report 08:00 CET | 08:00 CET | main | (empty message, unclear) | OK |

Target `main` means the job runs in the primary agent session (not an isolated sub-session).
## Critical problems identified 2026-04-09

### 1. OPERATIONSPLAN.md is stale (dated February 2026)

Buzz operates on an operations plan that is 6-8 weeks out of date:

- Claims API runs on port **8100** - actually runs on port **8000**
- Claims `run.py` is disabled due to port conflict - resolved weeks ago
- Claims agent count is **4.8M** - actually over **5M**
- North star is "AI Citation Rate baseline 0/21" - long surpassed
- No mention of: 23 languages, 18+ verticals, ZARQ, yield endpoints, Meta crawlers, ADR-002, Phase 0, expansion targets (50 languages / 100 verticals)

**Every 2 hours, Buzz reads this stale plan, runs a health check against port 8100 (which does not exist), the check times out, Buzz reports errors.**

### 2. Discord integration is broken

Gateway log shows continuous errors over past 24+ hours:

```
[discord] gateway: WebSocket connection closed with code 1005/1006
[ws] res sessions.resolve errorCode=INVALID_REQUEST errorMessage=No session found: discord#agentindex
[cron:<id>] cron delivery target is missing
```

**Anders has not been receiving Buzz reports** for at least a full day. The autonomous operator is running blind.

### 3. Newsletter job hardcoded to specific Claude model

Job 6 fails with: `model not allowed: anthropic/claude-sonnet-4-20250514`

Hardcoded model string somewhere in newsletter generation code. Has been failing for at least 2 weeks.

### 4. Uncertain relationship between Buzz and system_autoheal.py

`system_autoheal.py` is in the Nerq repo. The Buzz Health Check cron job says "Self-heal vid problem" but that is a natural-language instruction - Buzz decides how to interpret it. Whether Buzz actually calls `system_autoheal.py`, or runs shell commands directly, or does something else, is not documented.

On 2026-04-09 morning we spent 2+ hours debugging an autoheal restart loop. The fixes are committed (553a468, 18bbe80). But we cannot be certain those fixes affect Buzz because we do not know if Buzz reads that file.

## If you (future Claude) are asked about Nerq operations

1. **Read this file first.**
2. **Check `~/.openclaw/cron/jobs.json`** to see what Buzz is currently scheduled to do.
3. **Read `~/.openclaw/workspace/OPERATIONSPLAN.md`**. If still dated February 2026, propose updating it with Anders.
4. **Check `~/.openclaw/logs/gateway.log`** for recent Buzz activity and delivery failures.
5. **Look at `~/.openclaw/agents/main/sessions/<most-recent>.jsonl`** to see what Buzz has actually been doing recently. Large JSONL files but contain ground truth.
6. **Do not unload LaunchAgents assuming they stay unloaded.** Buzz may re-load them.
7. **Do not assume processes starting on their own are the system's fault.** Buzz may be starting them.
8. **Before architectural changes to Nerq, consider whether Buzz operations plan needs to be updated to reflect them.**

## Open options to discuss with Anders

Not decisions - things for Anders to weigh:

- **A: Update OPERATIONSPLAN.md** to reflect current Nerq state (2-4 hours of careful rewrite)
- **B: Fix Discord integration** so Anders regains visibility into Buzz (30-60 min)
- **C: Pause Buzz temporarily** if a fully controlled diagnostic window is needed (risky - Buzz does real work)
- **D: Audit Buzz recent sessions** by reading agents/main/sessions/*.jsonl to understand actual self-heal actions taken
- **E: Clean up failing jobs** (Job 6 failed for weeks, Jobs 2 and 4 timing out)

## Guiding principle

**Treat Buzz as a colleague, not a system component.** When Claude and Anders make operational changes, Buzz needs to know. When Buzz encounters the unknown, it should escalate via (working) Discord to Anders. When Anders is away, Buzz is driving. When Anders works with Claude, you and Buzz are co-workers sharing one Mac Studio.

## The hardest lesson from 2026-04-09

Nerq is a three-entity system (Anders + Buzz + Claude-session). I spent the morning treating it as two-entity (Anders + Claude) and was confused by the invisible third actor. Hours of diagnostic work chased symptoms that may have been caused or shaped by Buzz acting autonomously. The autoheal restart loop, specifically, remains a candidate explanation: Buzz may have been restarting uvicorn following its stale plan while we were trying to diagnose the restarts themselves.

Do not make the same mistake. Read this file. Know your colleague.
