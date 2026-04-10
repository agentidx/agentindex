# Ollama + Buzz discovery — 2026-04-10 morning

**Context:** Found during Leverage Sprint Day 1 pre-flight when running Ollama investigation as a Phase 0 preparation task. Started as a small question ("what uses Ollama?") and revealed a fundamental fact about the three-entity system that was not documented anywhere.

**Status:** Not a Leverage Sprint blocker. Is a Phase 0 blocker. Needs decision before ~2026-04-15 when Phase 0 execution begins.

---

## The core finding

Buzz runs entirely on local Ollama qwen3:8b. She does not call the Anthropic API at all. This is configured in ~/.openclaw/openclaw.json with the primary field set to custom-127-0-0-1-11434/qwen3:8b.

Every morning report, every health check, every self-heal decision, every Discord notification attempt goes through an 8B-parameter model running locally on Mac Studio on port 11434.

This was not documented in buzz-context.md, CLAUDE.md, or any ADR. The previous Claude session that set Buzz up knew this, but the knowledge did not propagate to subsequent session handoffs. It was discovered by grepping the codebase for ollama and 11434 references as part of a routine Phase 0 prep task.

## Why qwen3:8b is not sufficient

Evidence from Buzz's recent session logs in ~/.openclaw/agents/main/sessions/:

1. 2026-04-10 06:03 morning report attempt. Buzz called exec with a curl command checking port 8100 AND systemctl status agentprocessor. Two serious errors in one command:
   - Checking port 8100 (the stale port from the Feb 2026 OPERATIONSPLAN.md that was rewritten yesterday — Buzz either has not absorbed the new version or qwen3:8b failed to parse it correctly)
   - Using systemctl on macOS (Linux tool that does not exist on Darwin). The model does not know what OS it is running on despite it being literally in the system context.

2. 2026-04-10 06:03 same session, web_search attempts. Buzz tried to call web_search repeatedly without a Brave API key configured, logged the same error, and kept retrying. No adaptive behavior.

3. 2026-04-04 02:07-02:29 three identical "post-compaction audit" messages spaced 10 minutes apart. Buzz keeps generating the same reminder to herself about reading WORKFLOW_AUTO.md and asking "would you like me to read these files for you? 1/2/3". She does not realize she is talking to herself.

4. Buzz's own MEMORY.md says: "Ollama fungerar inte med OpenClaw pga kontextfonster-rapportering (4096 vs 16k minimum)". This is a known unresolved issue documented by a previous session and left unfixed.

## Why this matters for Phase 0

ADR-003 assumed Buzz could migrate to a Hetzner CPX41 node along with everything else. That assumption is broken:

- CPX41 specs: 8 vCPU AMD, 16 GB RAM, no GPU
- qwen3:8b requirements: ~6-8 GB RAM, runs at ~5-15 tokens/sec on CPU, usable but slow
- qwen3:32b or better (what Buzz probably needs): 24+ GB RAM, unusable on CPX41, requires Apple Silicon or GPU

Three possible Phase 0 paths. None decided today — this is for the Phase 0 decision window (~2026-04-15).

### Option A — Larger local model on Mac Studio, Buzz stays home

Mac Studio M1 Ultra has 64 GB unified RAM. It can run:
- qwen3:32b — likely good enough, ~20 GB RAM, runs at 15-25 tok/s on M1 Ultra
- llama3.3:70b-q4 — probably too much, 40+ GB RAM, slow
- qwen2.5:72b-q4 — similar to above

Consequence: Mac Studio becomes a permanent Buzz host, not an optional accelerator. Phase 0 only migrates the Nerq/ZARQ serving stack to Hetzner. Mac Studio is reclassified from "optional accelerator" to "required Buzz host + batch accelerator."

Cost: $0 extra. Already paid for.
Risk: Mac Studio hardware failure takes Buzz offline. The 2-5%/week risk that motivated Phase 0 in the first place still applies to Buzz specifically, but Buzz can run degraded without Nerq going down.
Estimated effort: 30-60 min to install the larger model, 1-2 hours to validate Buzz can actually use it without context-window issues.

### Option B — Hybrid: Anthropic API for hard tasks, local Ollama for trivia

smart_router.py already exists in the repo. It is designed exactly for this split but currently unused. Route decision tree:
- Morning report, strategic analysis, novel situations — Anthropic API (Sonnet or Haiku)
- Routine health checks, simple status parsing — local Ollama
- Self-heal decisions — Anthropic API (wrong decisions are expensive)

Cost: ~$20-50/month depending on volume. Well within Phase 0 budget cap of $100/month even combined with Hetzner costs.
Risk: Complexity. Two codepaths to maintain. Ollama failures still happen for the local-routed calls.
Estimated effort: 4-8 hours to wire smart_router.py into Buzz, test, and validate.

### Option C — Pure Anthropic API for Buzz

Simplest. Buzz stops using Ollama entirely. Mac Studio retires as LLM host and becomes pure batch/accelerator.

Cost: ~$50-150/month depending on how chatty Buzz is. Morning report alone is maybe ~10K tokens input + 2K output daily = ~$0.50/day = $15/month for that job. Health checks every 2 hours with smaller context = ~$10-20/month. Newsletter + competitor scans = variable. Estimate $50-100/month total.
Risk: Network dependency. If Anthropic is down or Mac Studio loses internet, Buzz is down.
Estimated effort: 2-4 hours to rip out Ollama calls and replace with Anthropic SDK calls. smart_router.py codebase already has the scaffolding.

### Non-option: qwen3:8b on Hetzner

Explicitly rejected. Hetzner CPU-only inference of an 8B model at acceptable latency for interactive tool use is not realistic, and the known context-window issue (4096 vs 16k minimum) would remain. This is a non-starter.

## What Buzz's current state looks like right now

As of 2026-04-10 ~08:30 CEST:

- Three Ollama processes running (PIDs 3576, 3700, 1425)
- Port 11434 listening (main Ollama server)
- Port 53680 listening (new runner started 08:39)
- Port 51356 listening (older runner)
- Buzz cron jobs continue to fire per schedule
- Morning report loop is failing silently (not delivered to Discord because Discord is also broken, not written to reports/ either apparently)
- No production impact — Buzz's failures are contained to her own workspace

She is awake but confused. She cannot successfully complete her assigned work but she is not actively harmful.

## Decision for today (2026-04-10)

Leave Buzz running as-is. Do not pause, do not restart, do not switch her model. Leverage Sprint Day 1 does not depend on Buzz being functional. Anders and this Claude session can run the sprint independently.

Rationale: stopping Buzz would introduce unknowns (do LaunchAgents re-load? does autoheal stop working? does any cron-scheduled batch break?). The cost of leaving her in a degraded-but-contained state for ~5 days is lower than the cost of touching her while we are in the middle of sprint work.

## Decision needed before 2026-04-15 (Phase 0 start)

Pick A, B, or C above. Anders to decide, this Claude session can write up cost/effort details for whichever option gets preliminary interest.

Initial lean from Anders (2026-04-10 morning): "Kanske ska vi ge Buzz en ny storre LLM som kan hantera nuvarande och framtida load." This points at Option A or a hybrid. Will flesh out on Phase 0 Day 1.

## Follow-up tasks

1. Fix OPERATIONSPLAN.md port references if any remain from pre-2026-04-09 rewrite — verify the new version does not contain 8100 anywhere. (Quick check, probably already correct, but worth confirming.)
2. Document Ollama in buzz-context.md — update buzz-context.md to explicitly state that Buzz runs on Ollama qwen3:8b, known-broken, Phase 0 decision pending.
3. Archive this file's findings in the next ADR-003 addendum — possibly Addendum #4 "Buzz migration strategy" once Option A/B/C is chosen.
4. Check whether smart_router.py is actually wired into anything — if it exists but is never called, remove it or activate it. Clean up operational debt.
5. Check whether auto_publisher.py, nerq_scout_agent.py, and the Ollama call in system_autoheal.py line 632 are actively used — these are production-adjacent Ollama consumers. If any of them are on cron or called by Buzz, they are also affected by whatever decision we make about Option A/B/C.

## References

- ~/.openclaw/openclaw.json — Buzz model config
- ~/.openclaw/workspace/MEMORY.md — Buzz's own note that Ollama+OpenClaw has context-window issues
- ~/.openclaw/agents/main/sessions/51979e6d-*.jsonl — 2026-04-10 06:03 morning report failure
- ~/.openclaw/agents/main/sessions/d14e0be2-*.jsonl — 2026-04-10 06:01 same session, web_search failures
- ~/agentindex/system_autoheal.py lines 205, 261, 632 — production Ollama calls
- ~/agentindex/agentindex/crypto/auto_publisher.py lines 19, 213 — crypto article Ollama calls
- ~/agentindex/agentindex/nerq_scout_agent.py lines 46, 447 — scout agent Ollama calls
- ~/agentindex/smart_router.py — unused router scaffolding

---

*End of Ollama + Buzz discovery document. Not a crisis. An important uncovered fact.*
