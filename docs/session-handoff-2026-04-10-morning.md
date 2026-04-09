# Session Handoff — 2026-04-10 Morning (Leverage Sprint Day 1)

**Previous sessions:** Claude chat 2026-04-09 (full day, ~10 hours, strategic planning + sequence reversal)
**This session's mission:** Start Leverage Sprint Day 1. Backup first, then audit + research + schema design across A1, A2, A3.
**Supersedes:** `docs/session-handoff-2026-04-09-evening.md` (the evening handoff was written before the sequence reversal; this morning handoff is the canonical start-here for 2026-04-10)

---

## Read first, in this exact order

1. **This file** — you are reading it
2. **`CLAUDE.md`** (repo root) — orientation, three-entity system, ground rules, operational conventions
3. **`docs/buzz-context.md`** — Buzz details, what she is, how to interact, what NOT to do
4. **`docs/adr/ADR-003-cloud-native-expansion-first.md`** — active architecture strategy
5. **`docs/adr/ADR-003-addendum-baseline-discoveries.md`** — discoveries from 2026-04-09 baseline capture
6. **`docs/adr/ADR-003-addendum-2-claude-code-local.md`** — Claude Code local execution capability (why LLM work is free)
7. **`docs/adr/ADR-003-addendum-3-sequence-revision.md`** — **why Leverage Sprint runs before Phase 0 (critical for understanding today's work)**
8. **`docs/strategy/leverage-sprint-plan.md`** — **today's and this week's execution plan**
9. **`docs/strategy/phase-0-cloud-migration-plan.md`** — Phase 0 plan (starts ~2026-04-15, not today)

Skip none of these. Step 7 in particular explains why we are doing Leverage Sprint today instead of provisioning Hetzner today. If you skip it you will be confused about why the canonical plan's Phase 0 isn't starting.

---

## What was decided 2026-04-09 (full day summary)

Yesterday's session started with the intent to build a Cloudflare R2 cache fallback Worker. It ended with a complete architecture replacement. The arc:

1. **Cost analysis killed the R2 approach.** At expansion scale, naive R2 caching would cost ~$220/month, exceeding the $100/month cap. This forced rethinking.

2. **ADR-003 written:** Cloud-native architecture with 2× Hetzner CPX41 + CPX21 worker, self-hosted Postgres with async replication, Mac Studio + Mac Mini demoted to optional accelerators, four-tier freshness SLA, render-on-demand. Budget $75-85/month flat.

3. **Phase 0-4 implementation plan written** covering cloud migration, Norwegian parameterization, 50-language sprint, vertical pipeline, 100-vertical sprint.

4. **OPERATIONSPLAN.md rewritten** for Buzz, reflecting new architecture and three-entity system.

5. **Baseline capture** revealed 8 important discoveries: ZARQ runs on SQLite, agent_jurisdiction_status is 57 GB (64% of DB), ZARQ has own MCP on port 8001, 47 LaunchAgents categorized, mcp-sse has sleep 5 race hack, existing Mac Studio → Mac Mini Postgres replication is live, etc. Documented in ADR-003 Addendum.

6. **Accounts provisioned:** Hetzner project 14112820 with SSH key, Backblaze B2 EU Central, Cloudflare Workers Paid (later flagged for downgrade since R2 approach is dead).

7. **Claude Code local execution discovered:** Anders noted Claude Code on Mac Studio + Mac Mini does not consume Anthropic API billing. Changed LLM cost for all phases from $200-400 to $0. Documented in ADR-003 Addendum #2.

8. **Leverage Sprint planned:** A1 Apple Intelligence optimization + A2 AI-to-human tracking + A3 Kings scaling 27K → 500K. Initially positioned after Phase 0.

9. **Sequence reversed on Anders's challenge:** Mac Mini was connected same day and stands idle. Momentum matters more than reducing 2-5% weekly hardware-failure risk. Leverage Sprint was moved to before Phase 0. Documented in ADR-003 Addendum #3. Leverage Sprint plan rewritten to reflect new sequence.

10. **Session ended** with everything committed to git and a clear Day 1 plan.

## Current system state (as of session start 2026-04-10)

- **Working tree:** should be clean. Verify with `cd ~/agentindex && git status`
- **HEAD:** multiple commits from 2026-04-09 including ADR-003, addenda #1-3, phase-0 plan, leverage sprint plan, and OPERATIONSPLAN.md rewrite
- **Production:** Mac Studio still serving everything, no infrastructure changes yet
- **Mac Mini:** connected, Postgres replica live (streaming to 100.115.230.106), idle, ready for first productive work
- **Buzz:** running on Mac Studio with updated OPERATIONSPLAN.md
- **Baseline:** intact at `~/nerq-baselines/2026-04-09-pre-migration/`
- **Hetzner + B2 accounts:** ready but nothing provisioned yet
- **Cloudflare Workers Paid:** still active (not yet downgraded — Anders can do this manually any time, it's not blocking)

## What you will do today (Day 1 of Leverage Sprint)

**Today's output is preparation, not production writes.** Day 1 is audit, research, schema design, and the pre-sprint backup. Actual deployments (A1 meta tags, A2 schema migration, A3 batches) start Day 2 based on today's findings.

### Morning block (2-3 hours): Pre-flight and backup

1. **Verify system state** — git clean, uptime stable, disk > 200 GB free (backup needs ~90 GB)
2. **Verify Mac Mini reachable** — ping via Tailscale, verify SSH works, verify Claude Code runs on it
3. **Run pre-sprint backup** — Postgres full dump + SQLite copies + sacred HTML refresh. See leverage-sprint-plan.md "Safety: backup before starting" section for the exact script. **This is blocking. Do not proceed without completed, verified backup.**
4. **Ollama investigation** — grep codebase for `ollama` and `11434` to find what uses it. If nothing obvious, ask Anders. This is one of the Phase 0 open decisions but we need to know before A3 enrichment starts.

### Afternoon block (3-4 hours): Three parallel research/design tracks

Split afternoon across A1, A2, A3. All are read-only or design-only — no production changes.

**A3 audit task** (1-2 hours):
```
Dig into the agentindex codebase to find what currently defines a "King" page.

Search for "king" or "King" references in:
- agentindex/ Python source files
- Templates (Jinja2 or similar)
- Database schemas / models
- SEO programmatic generation code

Find the automated check that classifies an entity as King vs non-King 
(search for `is_king`, `king_gate`, classification functions).

Document the complete definition in docs/architecture/kings-definition.md:
- Required JSON-LD blocks (which Schema.org types?)
- FAQ minimum (how many questions? any language requirements?)
- nerq:answer requirements (content, length, placement)
- Minimum content length
- Classification function location (file + line)
- Current count: how many Kings exist today? (should be ~27K)
- Any existing degraded Kings that need repair
- Sample URLs of current Kings for manual inspection
- Sample URLs of entities that just barely miss King status (for candidate ranking)

Do not make any changes. This is read-only audit.
```

**A1 research task** (1 hour):
```
Research Apple Intelligence crawler requirements and Nerq's current state 
relative to them.

1. Read agentindex/ for current robots.txt generation. Verify Applebot and 
   Applebot-Extended are allowed with no exclusions.

2. Look at current entity page HTML (fetch https://nerq.ai/safe/nordvpn via 
   curl) and check which Apple-specific meta tags exist vs are missing:
   - apple-mobile-web-app-capable
   - apple-mobile-web-app-status-bar-style
   - apple-mobile-web-app-title
   - apple-touch-icon (multiple sizes)
   - format-detection

3. Check current Schema.org markup for SoftwareApplication type. Identify 
   missing fields: applicationCategory, operatingSystem, softwareVersion, 
   offers, aggregateRating.

4. Measure TTFB from curl -w "%{time_starttransfer}" for:
   - https://nerq.ai/safe/nordvpn
   - https://nerq.ai/best/safest-vpns
   - https://nerq.ai/

5. Sketch the deploy plan for Day 2 without actually deploying:
   - Which files to edit
   - Which templates touch entity pages
   - How to validate golden file tests still pass

Write findings to docs/status/leverage-sprint-day-1-a1-research.md
```

**A2 schema design task** (1 hour):
```
Design the AI-to-human conversion tracking schema and deployment plan.

1. Read agentindex/logs/analytics.db schema for the requests table. 
   Document current columns and indices.

2. Design ALTER TABLE statements to add:
   - ai_source TEXT (nullable)
   - visitor_type TEXT (constraint: bot, human, ai_mediated)
   - Index on (ai_source, ts)

3. Design referer pattern matching logic:
   - claude.ai -> Claude
   - chat.openai.com / chatgpt.com -> ChatGPT
   - perplexity.ai -> Perplexity
   - copilot.microsoft.com / bing.com/chat -> Copilot
   - gemini.google.com -> Gemini
   - grok.x.ai / x.com/i/grok -> Grok
   - duckduckgo.com with AI params -> DuckAssist
   - kagi.com -> Kagi

4. Design user-agent pattern matching for AI-User clients:
   - ChatGPT-User -> ai_mediated visitor_type
   - Claude-User -> ai_mediated
   - Perplexity-User -> ai_mediated

5. Design backfill query that populates historical rows (where referer was 
   captured) with ai_source values.

6. Sketch dashboard query shapes for:
   - AI-to-human conversion rate (overall + per AI source)
   - Top URLs by AI-attributed visits
   - Language/vertical breakdown
   - 7-day trend

Write the design to docs/status/leverage-sprint-day-1-a2-schema.md. Do not 
deploy anything.
```

### End of day: commit and plan Day 2

1. **Commit all Day 1 outputs:**
   ```
   bash << 'EOF'
   cd ~/agentindex
   git add docs/architecture/kings-definition.md
   git add docs/status/leverage-sprint-day-1-a1-research.md
   git add docs/status/leverage-sprint-day-1-a2-schema.md
   git add docs/metrics/kings-candidates-2026-04-10.csv  # if generated
   git status
   git commit -m "leverage sprint day 1: audit, research, schema design

   A3: Kings definition documented with classification logic, current count,
       degraded Kings, sample URLs.
   A1: Apple Intelligence current state audited. Deploy plan for day 2.
   A2: AI-to-human tracking schema designed. Deployment plan for day 2."
   git push origin main
   git log --oneline -5
   EOF
   ```

2. **Session review with Anders** — show him the three Day 1 output documents and confirm Day 2 execution plan before ending the session.

3. **Prepare Day 2 task list** as a chat message for Anders to use in the next session or in Claude Code.

## Critical rules for today (and always)

- **Backup before any write.** The Safety section of leverage-sprint-plan.md is not optional. If backup fails, stop and diagnose.
- **No production writes on Day 1.** Everything today is read-only audit + design. Writes start Day 2.
- **Welcome all traffic.** Don't block or rate-limit any crawler without explicit Anders confirmation. This includes Meta crawlers.
- **Don't fight Buzz.** If you see processes starting that you didn't start, check git log and ps aux first. Might be Buzz doing normal operations per OPERATIONSPLAN.md.
- **Three-entity awareness.** Anders + Buzz + you. Buzz is a colleague running on Mac Studio (or eventually Nürnberg). Read `docs/buzz-context.md` if you haven't.
- **Sacred bytes drift = 0.** Never modify `pplx-verdict`, `ai-summary`, or `SpeakableSpecification` without explicit approval. Golden file tests from Phase 0 plan still apply.
- **Heredoc for shell commands.** Python for anything with markdown or special characters. Base64 for anything that needs to survive zsh+bash+markdown round-trips.
- **Commit often, push every time.** CI on every push. Failed CI blocks next step.
- **Ask before assuming.** Five minutes of clarification is cheaper than one hour of wrong execution.

## What NOT to do today

- **Don't provision Hetzner servers.** Phase 0 is deferred to ~2026-04-15. The accounts are ready but no servers should be created yet.
- **Don't start A3 Kings enrichment batches.** Those start Day 2 or Day 3 after audit + pipeline build.
- **Don't modify Mac Mini's Postgres configuration.** It is serving as a replica and should continue to do so. Just read from it.
- **Don't touch Cloudflare Tunnel configuration.** It keeps running until Phase 0 cutover.
- **Don't run any tight-loop API restarts.** Autoheal rules from 2026-04-09 are in effect.
- **Don't promise Applebot results.** Apple Intelligence is a black box. We optimize, we wait, we measure.
- **Don't rewrite OPERATIONSPLAN.md.** It was just updated yesterday. Leave it alone unless Anders asks.

## Known broken things (do not fix unless explicitly asked)

1. **Discord integration for Buzz** — broken since 2026-04-09, known issue, temp file-based reports channel at `~/.openclaw/workspace/reports/`
2. **Newsletter cron job** — hardcoded dead model string, known issue
3. **`stale_score_detector`** — schema drift against `entity_lookup.trust_calculated_at`, needs LEFT JOIN to agents. Will be fixed during A3 as part of Kings audit (A3 needs this tool working to measure Kings freshness).
4. **`compatibility_matrix`** — queries SQLite `npm_weekly` column that doesn't exist
5. **`yield_crawler_status`** — table missing from healthcheck.db
6. **Memory pressure on Mac Studio** — 95% RAM constant. Accepted risk. Phase 0 resolves by moving to Hetzner.
7. **Sudo-blocked fixes** — `scripts/apply_system_limits.sh`, auto-login, UPS. Sudo password unknown. Not blocking today.
8. **68% of internal links on localized pages lack language prefix** — known, tracked, not blocking today
9. **4 English uppercase strings leaking on Norwegian pages** — known, tracked, not blocking today

## Open questions carried from 2026-04-09

These don't block Day 1 but Anders may raise them:

1. **Does Buzz actually call `system_autoheal.py`?** Fixes committed yesterday (`553a468`, `18bbe80`) but never verified. Check `~/.openclaw/agents/main/sessions/` for recent Buzz activity if curious.
2. **What is Ollama used for?** This is Day 1 morning investigation task (grep codebase). If only Buzz uses it, it's not a blocker.
3. **Phase 0 other decisions:** ZARQ migration strategy, `agent_jurisdiction_status` trim, Cloudflare Workers Paid downgrade. These wait until Phase 0 approaches.
4. **Did Buzz write any reports to `~/.openclaw/workspace/reports/` overnight?** Check at start of session. If yes, they indicate Buzz read the new OPERATIONSPLAN.md.

## Success criteria for Day 1

Day 1 is successful if, by end of session:

- [ ] Backup complete and verified (Postgres + SQLite + sacred HTML)
- [ ] Mac Mini reachability confirmed (ping, SSH, Claude Code working on it)
- [ ] Ollama investigation complete (know what uses it, or know it's unused)
- [ ] Kings definition documented in `docs/architecture/kings-definition.md`
- [ ] A1 research document written with deploy plan for Day 2
- [ ] A2 schema design document written with deploy plan for Day 2
- [ ] All documents committed and pushed
- [ ] Day 2 task list drafted and ready for next session or Claude Code
- [ ] No production writes made (Day 1 is read-only)
- [ ] AI citation rate checked — no unexplained degradation from yesterday

If any of these fail, Day 2 starts with resolving the failure before continuing.

## Guiding principles (repeated because they matter)

- **Welcome all traffic.** Default is always "let them in."
- **Expansion-first.** 50 languages + 100 verticals before monetization. Trigger: 150K human visits/day × 7 days. Current: 10K-43K/day — still far from trigger.
- **Three-entity system.** Anders + Buzz + you. Coordinate, don't compete.
- **Momentum over robustness (when safe).** Yesterday's sequence reversal decision. Mac Studio's acute risks are mitigated. Build through the window while it's open.
- **Backup before write.** The single hardest rule to follow because it feels unnecessary until it isn't.
- **Not a coder.** Anders will not debug code for you. Do it yourself or explain clearly what you need verified.
- **Shell in heredoc.** Python for anything with markdown or special characters. Base64 for anything that needs to survive zsh+bash+markdown round-trips.
- **Ask before assuming.** Five minutes clarification vs one hour wrong execution.

---

## Files to reference during Day 1

**On Mac Studio filesystem:**
- `~/agentindex/CLAUDE.md` — ground rules
- `~/agentindex/docs/adr/ADR-003-*.md` — architecture (4 files: main + 3 addenda)
- `~/agentindex/docs/strategy/leverage-sprint-plan.md` — this week's work
- `~/agentindex/docs/strategy/phase-0-cloud-migration-plan.md` — next-week's work
- `~/agentindex/docs/session-handoff-2026-04-09-evening.md` — yesterday's context (superseded by this file but still useful background)
- `~/agentindex/docs/session-handoff-2026-04-10-morning.md` — this file
- `~/agentindex/docs/buzz-context.md` — colleague orientation
- `~/nerq-baselines/2026-04-09-pre-migration/` — yesterday's baseline data
- `~/.openclaw/workspace/OPERATIONSPLAN.md` — Buzz's operating instructions

**Not on Mac Studio yet (waiting to be created Day 1):**
- `~/nerq-backups/2026-04-10-pre-leverage-sprint/` — will contain pre-sprint backup
- `~/agentindex/docs/architecture/kings-definition.md` — A3 audit output
- `~/agentindex/docs/status/leverage-sprint-day-1-a1-research.md`
- `~/agentindex/docs/status/leverage-sprint-day-1-a2-schema.md`

## Session starts cleanly

Previous session ended with all work committed and a clear Day 1 plan. The Mac Mini connection is new, Hetzner + B2 accounts ready but unused, Leverage Sprint sequence-reversal is the most important context for understanding why today's work is what it is instead of Hetzner provisioning.

**First action:** Read the files in the order listed at the top of this document, then verify system state, then run the pre-sprint backup. Do not start any A1/A2/A3 work before backup is verified.

Good luck. Make momentum.

---

*End of session handoff for 2026-04-10 morning. Leverage Sprint Day 1 starts after backup is verified.*
