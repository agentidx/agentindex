# ADR-003 Addendum: Baseline Discoveries (2026-04-09)

**Parent:** ADR-003 Cloud-Native Expansion-First Architecture with Freshness SLA
**Date:** 2026-04-09 (evening)
**Author:** Claude session + Anders
**Status:** Accepted as addendum to ADR-003

## Context

After committing ADR-003 and phase-0-cloud-migration-plan.md earlier on 2026-04-09, a full baseline capture of the Mac Studio system revealed several facts that were not accounted for in the original decision. These discoveries do not invalidate ADR-003 but do require adjustments to the implementation plan for Phase 0. This addendum documents what was found, the impact on the plan, and the new decisions required.

The baseline itself is preserved at `~/nerq-baselines/2026-04-09-pre-migration/` on Mac Studio and includes system state, Postgres inventory, SQLite inventory, LaunchAgent inventory, sacred HTML snapshots, and copies of critical config files.

## Discoveries

### 1. ZARQ runs on SQLite, not PostgreSQL

The original ADR-003 assumed all operational data lived in the PostgreSQL database and that Postgres replication would cover both Nerq and ZARQ. Baseline capture revealed that ZARQ's core tables — `nerq_risk_signals`, `crash_model_v3_predictions`, `crypto_rating_daily`, `defi_protocol_tokens`, `crypto_pipeline_runs`, `crypto_ndd_history`, and others — live in `~/agentindex/agentindex/crypto/crypto_trust.db` (1.1 GB SQLite), not in Postgres.

**Impact:** Postgres replication (Mac Studio → Hetzner Nbg → Hetzner Hel) does not replicate ZARQ's data. ZARQ cannot survive Mac Studio loss under the current plan without additional work.

**Options (to be decided in Phase 0 Week 1):**

- **A. Migrate ZARQ tables to Postgres before cutover.** Adds 1-2 days to Phase 0. Cleanest long-term. Makes ZARQ a first-class citizen of the HA design.
- **B. Litestream or rsync-based SQLite replication to Hetzner.** Faster to implement (<1 day) but leaves ZARQ on SQLite, which is brittle at scale and reduces query flexibility.
- **C. Dual-deploy during transition: Nerq migrates to Hetzner first, ZARQ stays on Mac Studio until a Postgres migration is done post-Phase 0.** Pragmatic but extends the "Mac Studio is critical" window.

**Tentative preference:** Option A. ZARQ is a Tier 1 real-time product per the freshness SLA; degrading it to "rsync every N minutes" is worse than for analytics. But the final decision is deferred to Phase 0 Day 2 after examining the schema complexity.

### 2. `agent_jurisdiction_status` is 57 GB — 64% of the entire database

Postgres baseline shows the database is 89 GB total. The single largest table, `agent_jurisdiction_status`, is 57 GB. This table holds 52 jurisdictions × 5M agents = ~260 million rows.

**Impact:** The initial Postgres transfer over Tailscale from Mac Studio to Hetzner Nürnberg was estimated at 6-8 hours for an 80 GB database. The actual database is 89 GB and more than half of that is a single very-wide table. Transfer time estimate is revised to 8-14 hours.

**Options:**

- **A. Transfer as-is.** Accept the 8-14 hour window. Run it during a low-traffic overnight period.
- **B. Trim the table before transfer.** Only transfer active (non-archived) jurisdiction statuses, or compress historical data, or trim unused jurisdictions. This could cut the table by 50% or more.
- **C. Investigate table design.** 260M rows for 5M agents × 52 jurisdictions suggests a wide-row pattern that may be inefficient. A pivot to a more compact schema could reduce the size to <10 GB. This is a bigger refactor and belongs post-Phase 0.

**Tentative preference:** Option A for the migration itself (don't block on refactor), but flag Option C as a follow-up task. The `agent_jurisdiction_status` schema deserves a review after cloud migration is stable.

### 3. ZARQ has its own MCP server on port 8001

Baseline revealed `com.zarq.mcp-sse` — a separate LaunchAgent running `zarq_mcp_server.py` on port 8001. This is distinct from the Nerq MCP server (`com.agentindex.mcp-sse` on the standard port). ADR-003 mentioned the Nerq MCP server but did not account for ZARQ having its own.

**Impact:** The FastAPI deployment on Hetzner must include both MCP servers. Port allocation on the Hetzner nodes needs to reserve both 8000 (Nerq API) and 8001 (ZARQ MCP). The Cloudflare routing for `mcp.nerq.ai` and any equivalent ZARQ MCP endpoint must be verified and preserved.

**Action:** Add both MCP servers to the deployment checklist in Phase 0 Week 2. Test both endpoints in the staging phase before cutover.

### 4. Two cloudflared processes running (likely duplicate)

Baseline shows `com.cloudflare.cloudflared` (actively running `cloudflared tunnel run agentindex`) AND `homebrew.mxcl.cloudflared` (running the binary without arguments). The second one is almost certainly a legacy or duplicate that does nothing useful.

**Impact:** Minor. Since the Cloudflare Tunnel is being decommissioned during Phase 0 cutover, both of these go away regardless. But it is a symptom of accumulated operational debt and is worth noting in the cutover checklist to ensure both are removed cleanly.

**Action:** During Phase 0 cutover, verify both LaunchAgents are unloaded and their plists removed.

### 5. Ollama is running as a LaunchAgent

`homebrew.mxcl.ollama` is active. Its purpose on Mac Studio is unclear — possibly a local LLM for Buzz self-heal decisions, possibly a remnant from an earlier experiment, possibly used by one of the crawlers or classifiers.

**Impact:** Unknown. Before decommissioning Mac Studio as primary, we need to identify what depends on Ollama. If Buzz needs local LLM inference, the Hetzner CPX41 nodes cannot run Ollama at reasonable performance without a GPU, so this dependency would need to be broken or replaced with API calls.

**Action:** Phase 0 Day 1 task — ask Anders what Ollama is used for, or grep the codebase for `ollama` / `localhost:11434` references to identify the consumer(s). If Buzz is the only consumer and we migrate Buzz to Nürnberg, we need to decide whether Buzz switches to Claude API calls or keeps local Ollama on Mac Studio as an accelerator dependency.

### 6. Postgres replication Mac Studio → Mac Mini is already live

Baseline shows `postgres: walsender replicator 100.115.230.106(57921) streaming 2C8/E9B677C0`. This is a WAL sender actively streaming to Mac Mini's Tailscale IP. The replica setup from ADR-002 Phase 0 (performed 2026-04-08) is still active.

**Impact:** Positive. We have a working streaming replication configuration we can model the Hetzner setup on. The `pg_hba.conf` and `postgresql.conf` are already set up for replication (baseline has copies). The `replicator` user and replication slot are already in place. Setting up Hetzner as a second replica should be straightforward: same approach, different destination IP.

**Action:** Use the existing Mac Mini replication config as a template for the Hetzner setup. Mac Mini can remain as a local replica during the transition — it does no harm and provides an extra safety net.

### 7. 47 Nerq/ZARQ LaunchAgents categorized

The full LaunchAgent inventory identified 50 plists (47 Nerq/ZARQ plus 3 Google). They fall into three groups for migration purposes:

**Must migrate to Hetzner (production-critical):** `com.nerq.api`, `com.agentindex.mcp-sse`, `com.zarq.mcp-sse`, `com.agentindex.dashboard`, `com.agentindex.parser`, `homebrew.mxcl.postgresql@16`, `homebrew.mxcl.redis`, `com.nerq.master-watchdog`, `com.nerq.performance-guardian`, plus the high-frequency cache refresh jobs (`zarq-cache` every 4 min, `yield-orchestrator` every 15 min, `analytics-cache` every 30 min, `cache-warmer` hourly, `reach-dashboard` hourly, `analytics-weekly-cache`).

**Can stay on Mac Studio as accelerator** (heavy enrichment, non-time-critical): all crawlers (`npm-bulk-enricher`, `npm-crawler`, `nuget-downloads`, `chrome-users`, `firefox-users`, `go-github-stars`, `openssf-crawler`, `osv-crawler`, `compat-matrix`, `community-signals`, `scout`), crypto batch jobs (`crypto-daily`, `dex-volumes`, `paper-trading-daily`, `vitality-recalc`, `vitality-report`), reports and KPI jobs (`daily-scores`, `signal-warehouse`, `dashboard-data`, `cve-alerts`, `kpi-csv`, `capacity-check`, `auto-indexnow`, `badge-responder`, `badge-outreach`, `king-refresh`, `daily-backup`).

**Not needed post-cutover:** `com.cloudflare.cloudflared` and `homebrew.mxcl.cloudflared` (tunnel decommissioned), `ai.openclaw.gateway` (Buzz migrates to Nürnberg).

**Broken, fix before migrating:** `com.nerq.stale-scores` — known schema drift against `entity_lookup.trust_calculated_at`. Fix this during Phase 0 as part of the freshness SLA observability work, then migrate.

**Uncertain:** `homebrew.mxcl.ollama` — see discovery #5.

### 8. `com.agentindex.mcp-sse` contains a `sleep 5` race-condition hack

The Nerq MCP server LaunchAgent runs `/bin/bash -c sleep 5 && exec .../mcp_sse_server`. This is a workaround for a race condition where the MCP server must start after the main API. It works but is fragile.

**Impact:** When we deploy to Hetzner, we should either (a) replicate the sleep to preserve current behavior, or (b) fix the underlying race condition with proper systemd service dependencies (`After=` and `Requires=`). Option (b) is better because it's correct, but it adds work to Phase 0 Week 2.

**Action:** Replicate the sleep hack initially to keep cutover risk low. Log as a follow-up task to fix properly once the Hetzner deployment is stable.

## Impact on Phase 0 plan

The phase-0-cloud-migration-plan.md does not need to be rewritten, but the following adjustments apply to Phase 0 Week 1:

1. **Day 2 decision point:** ZARQ migration strategy (A/B/C above). Must be decided before Postgres transfer begins.
2. **Day 3-4 Postgres transfer window:** Budget 8-14 hours instead of 6-8. Run overnight.
3. **Day 1 investigation task:** Identify Ollama consumers.
4. **Day 5-6 ZARQ deployment:** Include `zarq_mcp_server` on port 8001 in the deployment, not just the Nerq FastAPI app.
5. **Week 2 cutover checklist additions:** Both cloudflared LaunchAgents unloaded, Ollama dependency resolved or replicated, MCP endpoint tests include ZARQ's MCP on 8001.

## Decisions deferred to Phase 0 Day 1

1. ZARQ migration strategy (Option A, B, or C)
2. Ollama handling (migrate, replace with API calls, or leave on Mac Studio as accelerator dependency)
3. Cloudflare Workers Paid plan — downgrade to Free now that R2-cache-fallback approach is dead, or keep as future option (~$5/month). Tentative preference: downgrade to save $5/month pre-revenue.
4. `agent_jurisdiction_status` trim-before-transfer (Option A, B, or C under discovery #2)

## No change to core ADR-003 decisions

None of these discoveries invalidate the core ADR-003 decisions:

- Cloud-native architecture with 2× Hetzner CPX41 + 1× CPX21 worker ✓
- Self-hosted Postgres with async replication ✓
- Mac Studio + Mac Mini as optional accelerators ✓
- Freshness SLA in four tiers ✓
- Render-on-demand ✓
- Budget cap at $100/month ✓
- Phase 0-4 sequence (cloud migration → parameterize Norwegian → 50 languages → vertical pipeline → 100 verticals) ✓

## References

- ADR-003: `docs/adr/ADR-003-cloud-native-expansion-first.md`
- Phase 0 plan: `docs/strategy/phase-0-cloud-migration-plan.md`
- Baseline data: `~/nerq-baselines/2026-04-09-pre-migration/` on Mac Studio
- LaunchAgent summary: `~/nerq-baselines/2026-04-09-pre-migration/launchagents-summary.txt`
- Session handoff: `docs/session-handoff-2026-04-09-evening.md`

---

*End of ADR-003 Addendum.*
