# Phase 0 — Cloud Migration and Expansion Acceleration Plan

**Period:** 2026-04-09 through ~2026-05-28 (5-8 weeks total)
**Implements:** ADR-003 (Cloud-Native Expansion-First Architecture with Freshness SLA)
**Supersedes:** `docs/strategy/phase-0-1-implementation-plan.md`

---

## Overview

This plan describes how to migrate Nerq and ZARQ from Mac Studio to a cloud-native architecture, then accelerate expansion to 50 languages and 100 verticals, then establish a continuous freshness SLA operation. It is organized into five phases:

| Phase | Goal | Duration | Blocking? |
|---|---|---|---|
| **0** | Cloud migration + DR + Buzz relocation | 2 weeks | Yes, blocks new vertical expansion |
| **1** | Parameterize the Norwegian language-addition model | 3-5 days | Yes, blocks 50-language sprint |
| **2** | 50-language sprint (22 → 50) | 5-10 days | Runs in parallel with Phase 3 |
| **3** | Vertical pipeline architecture | 3-5 days | Yes, blocks 100-vertical sprint |
| **4** | 100-vertical sprint (14 → 100) | 2-3 weeks | Runs after Phases 1-3 complete |
| **Ongoing** | Freshness SLA operations | Permanent | Starts during Phase 0, matures across all phases |

Phase 0 is the only phase that pauses new vertical expansion. Language expansion and hidden registry fixes continue on Mac Studio during Phase 0. Monetization preparation (affiliate signups) also continues in parallel per the expansion master plan.

---

## Working methodology

This plan assumes the same collaboration model as previous phases, with one important refinement based on the 2026-04-09 session:

1. **Claude (chat session) designs, writes critical code, and reviews.** Writes every file that involves Postgres replication, Cloudflare configuration, Patroni setup, the freshness SLA module, and the parameterized language pipeline.
2. **Claude Code (on Mac Studio or Hetzner) executes mechanical work** — running installation scripts, applying migrations, running audits. Each Claude Code session receives a specific prompt with clear acceptance criteria.
3. **Buzz is informed before operational changes.** Before any Phase 0 step that affects production, the Buzz OPERATIONSPLAN.md is updated so Buzz does not fight the migration. This is a prerequisite for Phase 0 Day 1.
4. **Anders runs commands interactively, pastes output back for verification.** Commands always in heredoc format. Python is preferred for anything with markdown, multi-line text, or special characters.
5. **Every phase ends with an explicit review.** No phase proceeds until its done-criteria are checked.

### Universal rules

- Never modify the `pplx-verdict`, `ai-summary`, or `SpeakableSpecification` sacred elements without explicit approval. Golden file tests from the previous phase-0-1 plan carry forward and remain in CI.
- Every change has a rollback procedure, documented before the change is made.
- Commit often, push every time. CI must pass on every commit.
- When in doubt, ask in chat. Five minutes of clarification is cheaper than one hour of incorrect execution.

---

## Phase 0 — Cloud migration (2 weeks)

The goal of Phase 0 is: at the end of week 2, serve 100% of nerq.ai and zarq.ai traffic from Hetzner nodes, with Mac Studio demoted to optional accelerator status, with Buzz running on the Nürnberg node, and with full DR (B2 backups verified, automatic Hetzner failover tested).

### Week 1 — Provisioning and data migration

**Week 1 goals:**
- Both Hetzner CPX41 nodes provisioned, hardened, and on Tailscale
- Postgres 16 installed on both, async streaming replication live
- Initial full Postgres dump from Mac Studio transferred to Nürnberg (the 80 GB transfer is the biggest risk item in the entire migration)
- Backblaze B2 bucket created, pgBackRest configured, first full backup completed and restore-verified
- CPX21 worker node provisioned
- Buzz OPERATIONSPLAN.md updated to reflect the migration in progress, so Buzz does not interfere

**Risk items:**
1. **80 GB Postgres transfer.** This is the single biggest fragility point. Two options: (a) `pg_dump` to a file on Mac Studio, scp/rsync to Nürnberg, restore there; (b) `pg_basebackup` directly over Tailscale. Option (a) is slower but resumable on failure. Option (b) is faster but a dropped connection means starting over. **Default: option (a).** Expected duration: 4-8 hours depending on bandwidth.
2. **Tailscale stability over long-running operations.** If Tailscale hiccups mid-transfer, option (a) is resumable via `rsync --partial`. Option (b) is not.
3. **Buzz interference.** If Buzz's health checks fire during the migration and Buzz "fixes" something that is intentionally down, we lose time. Must be addressed on day 1.

**Done criteria (Week 1):**
- [ ] Nürnberg CPX41 provisioned, Tailscale joined, firewall configured, Postgres 16 installed
- [ ] Helsinki CPX41 provisioned, same setup
- [ ] CPX21 worker provisioned
- [ ] Full Postgres dump transferred and restored on Nürnberg, row counts match Mac Studio
- [ ] Async streaming replication Nbg → Hel configured and verified (test row round-trip < 1 second)
- [ ] Backblaze B2 bucket created, pgBackRest configured on Nürnberg, first full backup uploaded
- [ ] Restore verification test: backup restored into a throwaway Postgres instance, sanity queries pass
- [ ] Buzz OPERATIONSPLAN.md updated with migration context (at minimum: "cloud migration in progress 2026-04-09 through 2026-04-23, do not attempt to restart services on Hetzner nodes")
- [ ] Anders has SSH access to all three Hetzner nodes as the `nerq` user

### Week 2 — Application migration and cutover

**Week 2 goals:**
- FastAPI app deployed to both Hetzner nodes, tested in staging
- Cloudflare Load Balancer configured with health checks
- Cloudflare DNS updated to point to Hetzner origins
- Cloudflare Tunnel decommissioned
- Patroni (or pg_auto_failover) configured for automatic Postgres failover
- Buzz migrated to Nürnberg, Mac Studio demoted to secondary
- SQLite analytics rsync running every 10 minutes to both Helsinki and B2
- Freshness SLA observability dashboard live (initial version, before Phase 1)
- Full cutover from Mac Studio to Hetzner primary

**Cutover sequence (Day 10):**

1. **Morning:** Final sync of Postgres (streaming replication is already live, just verify zero lag)
2. **Morning:** Final sync of SQLite analytics via rsync
3. **Midday:** Deploy FastAPI app to both Hetzner nodes from latest main branch
4. **Midday:** Staging test — hit every page type on both Hetzner nodes via their public IPs directly, verify sacred elements render correctly
5. **Afternoon:** Canary — flip 10% of nerq.ai traffic to Hetzner Nürnberg via Cloudflare Load Balancer weighted routing
6. **Afternoon:** Watch dashboards for 2 hours. AI citation rate, error rate, latency, sacred-element drift all checked.
7. **Evening:** If canary is clean, flip to 100% Hetzner. Mac Studio still running as hot fallback.
8. **Next day:** 24-hour observation. If clean, decommission Cloudflare Tunnel.
9. **Day after:** Demote Buzz on Mac Studio to secondary instance. Primary Buzz now runs on Nürnberg.

**Rollback:** A single Cloudflare Load Balancer rule change routes traffic back to Mac Studio in under 60 seconds. Mac Studio remains fully warm throughout Phase 0 for exactly this reason.

**Done criteria (Week 2 / Phase 0 complete):**
- [ ] FastAPI app deployed and running on both Hetzner CPX41 nodes
- [ ] Cloudflare Load Balancer health checks configured and firing
- [ ] nerq.ai and zarq.ai serving 100% from Hetzner for 24+ hours
- [ ] AI citation rate within normal variance (Day 1 baseline)
- [ ] Sacred bytes drift = 0 on all golden file tests
- [ ] Cloudflare Tunnel decommissioned (or scheduled for deletion within 7 days)
- [ ] Patroni configured and tested with a manual failover drill (traffic continues serving through a deliberate primary-kill test)
- [ ] Buzz primary instance running on Nürnberg, Mac Studio as secondary
- [ ] SQLite analytics rsync running every 10 min
- [ ] Initial freshness SLA dashboard live showing per-tier compliance
- [ ] pgBackRest running on schedule (hourly WAL, nightly full, weekly full-verify)
- [ ] Phase 0 retrospective written

---

## Phase 1 — Parameterize the Norwegian model (3-5 days)

**Goal:** Convert the Norwegian language-addition process from 700 lines of manual Claude Code edits per language into a declarative `language_config.yaml` + `add_language.py` pipeline.

### Context

The Norwegian addition process edited 8 files: `translations.py`, `localized_routes.py`, `homepage_i18n.py`, `nerq_design.py`, `seo_programmatic.py`, `analytics_dashboard.py`, `flywheel_dashboard.py`, and `agent_safety_pages.py`. Each edit involved ~232 phrase translations, ~54 UI strings, an 11-string FAQ tuple, a ~100-line regex block for dynamic text patterns, travel/charity/health localizations, and analytics dashboard ordering. The work took hours of Claude Code time plus extensive manual audit.

At that pace, 27 new languages would take weeks of serial work. Parameterization is a hard prerequisite for the 50-language sprint.

### Deliverables

1. **`agentindex/i18n/language_config.yaml`** — schema for a single language config. Includes native name, RTL flag, reference language for translation, all 232 phrase mappings, UI strings, FAQ tuple, regex patterns, and dashboard ordering hints.
2. **`agentindex/i18n/languages/`** — directory with one YAML file per language. Initial commit includes the 23 existing languages, each extracted from the current Python dictionaries into the YAML format.
3. **`scripts/add_language.py`** — reads a language YAML, performs all 8 file edits, runs validation, and reports success or specific failures.
4. **`scripts/validate_language.py`** — automated audit that checks: no English strings leak through on localized pages, all keys are translated, SpeakableSpecification is intact, sacred elements render correctly, and dashboard orderings are consistent.
5. **`scripts/generate_language_from_ai.py`** — given a target language code and a reference language, produces a draft YAML config using an LLM. Human review required before the config is used.

### Acceptance test

The existing 23 languages must render identically before and after the parameterization. Concretely: for each existing language, diff the current rendered output of 10 representative pages against the output after running `add_language.py` from the extracted YAML. Diff must be empty.

### Timeline

- Days 1-2: Extract existing Python translation dictionaries into YAML configs for all 23 languages. Verify byte-identical rendering.
- Day 3: Build `add_language.py` and `validate_language.py`. Test by re-adding an existing language from its YAML.
- Day 4: Build `generate_language_from_ai.py`. Test by generating a draft for a target language (e.g., Finnish).
- Day 5: End-to-end test — add Finnish (or another yet-unadded language) via the full pipeline, audit manually, confirm it passes the same 10/10 quality bar the Norwegian addition required.

### Done criteria

- [ ] YAML schema documented and committed
- [ ] 23 existing languages extracted to YAML, byte-identical rendering verified
- [ ] `add_language.py`, `validate_language.py`, and `generate_language_from_ai.py` implemented and tested
- [ ] One new language added via the pipeline and passes manual audit
- [ ] Phase 1 retrospective written, including time per language and specific audit issues found

---

## Phase 2 — 50-language sprint (5-10 days)

**Goal:** Add 27 new languages to bring the total from 23 to 50, using the parameterized pipeline from Phase 1.

### Language prioritization

Order by a weighted combination of:

1. **Population of native speakers** (raw reach)
2. **AI bot traffic share** from that country (indicator of AI-driven demand)
3. **Yield per language** from existing data (Japanese 28.5%, Portuguese 27%, German 24.9% as reference — high yield per localized page)
4. **Language family proximity** to existing languages (cheaper AI draft translations)

Proposed first batch (4-6 languages per day):
- **Batch 1:** Finnish, Ukrainian, Hebrew, Greek (diverse families, medium reach)
- **Batch 2:** Bengali, Tamil, Urdu, Punjabi (India/Pakistan — large speaker base, low competition)
- **Batch 3:** Farsi, Arabic dialects (if not already covered), Swahili, Hausa (underserved regions)
- **Batches 4-6:** Filipino/Tagalog, Vietnamese dialects, Malay expansions, Thai regional, etc.

Specific ordering is a Phase 2 Day 1 decision based on fresh AI citation data from the per-language yield dashboard.

### Execution

- Batches of 4-8 languages run in parallel using `add_language.py`
- Each batch runs on burst CPX51 or Mac Mini (if healthy) to avoid competing with production on the Hetzner serving nodes
- After each batch, automated validation runs, then a manual spot-audit of 5 pages per language
- Any language failing spot-audit is held back and debugged before the next batch starts

### Quality floor

No language ships if:
- English strings leak through on localized pages (hard fail)
- Sacred elements fail to render (hard fail)
- Trust score values display incorrectly (hard fail)
- Native speaker spot-check scores below 7/10 (soft fail, investigate before shipping)

### Timeline

- Days 1-2: Batch 1 build + audit + ship
- Days 3-4: Batch 2 + Batch 3 in parallel
- Days 5-7: Batches 4-6
- Days 8-10: Cleanup, French yield diagnostic (why 11.6% vs German 24.9%), stragglers

### Done criteria

- [ ] 50 languages live on nerq.ai
- [ ] All 50 pass automated validation (no English leakage, sacred elements intact)
- [ ] Spot audits complete for each language, failures documented and resolved
- [ ] Per-language yield dashboard updated with new language IDs
- [ ] Sitemap chain updated (new language sitemaps added to the parent)
- [ ] IndexNow batch-ping submitted for all new URLs
- [ ] French yield diagnostic completed, root cause documented
- [ ] Phase 2 retrospective written

---

## Phase 3 — Vertical pipeline architecture (3-5 days, parallel with Phase 2)

**Goal:** Build a declarative vertical-building pipeline that makes the 100-vertical sprint possible.

### Context

The existing 14 verticals were built as hardcoded vertical-specific code. Each new vertical involved creating new templates, new rendering functions, new registry logic, and manual integration with the navigation, sitemap, homepage grid, and analytics dashboard. At that pace, 86 new verticals would take months.

The vertical pipeline replaces this with a config-driven approach where a single YAML file defines a vertical and all the rendering, integration, and validation flows from it.

### Deliverables

1. **`agentindex/verticals/vertical_config.yaml`** — schema for a vertical definition. Includes data sources, trust score model, page types, `/best/` listicles, localization requirements, sacred element validation rules, IndexNow priority, freshness tier assignment, and cross-link groups.
2. **`agentindex/verticals/configs/`** — directory with one YAML per vertical. Initial commit extracts the 14 existing verticals into this format.
3. **`agentindex/verticals/build_orchestrator.py`** — reads a vertical config, triggers data acquisition, computes trust scores, renders all page types in all languages, validates sacred elements, and commits results to Postgres.
4. **Generic templates** — existing hardcoded per-vertical Jinja templates refactored to accept configuration. One template file per page type, not one per vertical per page type.
5. **`scripts/add_vertical.py`** — CLI wrapper around the orchestrator for building a single vertical from its config.

### Acceptance test

All 14 existing verticals must render identically before and after the refactor. Same byte-identical diff approach as Phase 1.

### Hidden registry fix

This phase is also the right time to fix the quality gate for hidden registries (chrome, nuget, go, firefox, vscode, packagist, gems) per Prio A of the expansion master plan. Fixing these unlocks ~810K entities across 5-7 "new" verticals with near-zero build effort. The fix is scoring-distribution based and takes hours, not days, so it fits naturally into Phase 3.

### Done criteria

- [ ] Vertical config schema documented and committed
- [ ] 14 existing verticals extracted to YAML, byte-identical rendering verified
- [ ] `build_orchestrator.py` and `add_vertical.py` implemented and tested
- [ ] Generic templates replacing all hardcoded per-vertical rendering
- [ ] Quality gate fixed for chrome, nuget, go, firefox, vscode, packagist, gems
- [ ] 5-7 hidden registries now live as verticals via the new pipeline
- [ ] Phase 3 retrospective written

---

## Phase 4 — 100-vertical sprint (2-3 weeks)

**Goal:** Grow from ~20 verticals (14 original + 5-7 unhidden in Phase 3) to 100 verticals using the pipeline from Phase 3 and the fas-ordering from the expansion master plan (Ring 4 and Ring 5).

### Execution model

Unlike languages (which are mostly translation work), verticals are mostly data and curation. The pipeline handles integration, but data sources and trust-component choices require vertical-specific thought. Anders (or Buzz, or a Claude Code session with clear scope) must specify for each vertical:

- Which data sources feed it
- Which trust components apply
- Which `/best/` listicles to generate
- Which cross-link groups it joins (Security Stack, Business Stack, Dev Stack, etc.)

### Batching

Verticals are built in batches of 4-6 in parallel using burst compute (CPX51 or Mac Studio if healthy). Each batch:

1. Config files written (Anders + Claude or Claude Code)
2. Configs reviewed in chat before commit
3. Orchestrator runs for the batch
4. Automated validation per vertical
5. Spot-audit per vertical
6. IndexNow batch-ping + sitemap update + homepage grid + nav mega-dropdown update
7. Flywheel dashboard check after 24 hours, AI citation check after 72 hours

### Ring 4 and Ring 5 reference

See `docs/strategy/nerq-vertical-expansion-master-plan-v3.md` for the canonical fas-ordering. This plan implements Fas 7 through Fas 22+ via the new pipeline.

### Done criteria

- [ ] 100 verticals live on nerq.ai
- [ ] All 100 × 50 languages passing automated validation
- [ ] Cross-link mesh network fully established per the expansion master plan
- [ ] Homepage grid and nav mega-dropdown updated
- [ ] Sitemap chain complete
- [ ] Freshness tier assignments made for every vertical
- [ ] Phase 4 retrospective written

---

## Ongoing — Freshness SLA operations

**Goal:** Establish permanent operations that keep the four-tier freshness SLA honest across all entities, in perpetuity.

### Components

1. **Signal fetchers (always-on, CPX21):**
   - Crypto: WebSocket streams from DeFiLlama, CoinGecko, Etherscan → Postgres
   - Package registries: npm dumps, PyPI, GHSA, OSV → scheduled bulk ingestion
   - Website trust signals: per-vertical scrapers running on schedule
2. **Scoring workers:**
   - **Tier 1 (event-driven):** DeFiLlama event triggers Postgres notify → Tier 1 entity rescore within seconds
   - **Tier 2 (15-minute batch):** cron on CPX21 re-scores top 1000 entities based on analytics
   - **Tier 3 (daily):** cron on CPX21 re-scores all entities with new signals in last 24h
   - **Tier 4 (weekly):** scheduled burst CPX51 runs full re-score of all 5M entities
3. **Cache invalidation + IndexNow pipeline:**
   - Score update triggers Postgres notify → invalidator service → Cloudflare cache purge + IndexNow ping + sitemap lastmod bump
   - Event-driven, triggered per-entity-update
4. **Freshness observability:**
   - `stale_score_detector` fixed (current schema drift against `entity_lookup.trust_calculated_at` resolved via LEFT JOIN to `agents` table)
   - Dashboard showing per-tier SLA compliance (percentage of entities within SLA)
   - Alertmanager rules firing when any tier drops below 95% compliance for >1 hour
5. **Public freshness claims:**
   - Footer of relevant pages displays "Last updated: X seconds/minutes/hours ago" per entity tier
   - llms.txt WHEN-TO-CITE patterns updated to reference freshness guarantees
   - Marketing copy updated to reflect four-tier SLA

### Phase entry

Freshness SLA work starts during Phase 0 (initial dashboard) and matures across every subsequent phase. By the end of Phase 4, all components are live and operating at steady state.

### Done criteria (reached at steady state, not as a sprint checkpoint)

- [ ] All four tiers have active signal fetchers and scoring workers
- [ ] `freshness_policy.py` module is the single source of truth for tier assignment
- [ ] Cache invalidation pipeline is event-driven and tested
- [ ] Dashboard shows >95% SLA compliance across all four tiers
- [ ] Alerts fire correctly in drill tests
- [ ] Footer freshness indicators live on all entity pages
- [ ] Marketing claims updated to reflect measurable SLA

---

## Success metrics for the full plan

The plan is successful if, at the end of Phase 4:

1. **Both machines in Stockholm can die and the system continues serving.** Verified via a drill where Mac Studio and Mac Mini are deliberately taken offline for 4 hours. No user-visible degradation.
2. **50 languages are live** with no English leakage and passing automated validation.
3. **100 verticals are live** with full cross-link mesh and correct freshness tier assignment.
4. **Freshness SLA compliance is >95% across all four tiers** for a sustained 7-day window.
5. **Monthly infrastructure cost stays under $100.**
6. **AI citation rate has not degraded** relative to the 2026-04-09 baseline — ideally grown as new languages and verticals attract more citations.
7. **Monetization trigger remains on track** — 150K human visits/day sustained for 7 days — without architectural debt.
8. **Buzz operates continuously across the migration** with OPERATIONSPLAN.md kept current.

If any of these fail, the associated phase is re-opened and the failure is resolved before declaring the plan complete.

---

## Rollback procedures

Every phase has a documented rollback. The most critical ones:

- **Phase 0 Week 1 rollback:** If Postgres transfer fails or Tailscale proves too unstable, pause, debug, and retry. No production impact — Mac Studio remains primary throughout Week 1.
- **Phase 0 Week 2 cutover rollback:** Single Cloudflare Load Balancer rule change returns traffic to Mac Studio. Sub-60-second rollback. Mac Studio is kept warm for 7+ days post-cutover for exactly this scenario.
- **Phase 1 rollback:** If parameterization introduces regressions in existing 23 languages, revert commits. Nothing customer-facing is affected until the new pipeline is actually used to add a new language.
- **Phase 2 rollback per language:** Each new language is independently revertable by removing its YAML and re-running the build. A bad language does not affect other languages.
- **Phase 3 rollback:** Vertical pipeline work happens alongside the existing hardcoded verticals. If the refactor fails, the old hardcoded path still works.
- **Phase 4 rollback per vertical:** Each new vertical is independently revertable.

No phase requires a rollback that affects a preceding phase. Phases are additive.

---

## Dependencies and prerequisites

Before Phase 0 Day 1:

- [ ] ADR-003 committed to `docs/adr/`
- [ ] This plan committed to `docs/strategy/`
- [ ] Buzz OPERATIONSPLAN.md updated with migration context (blocker for Day 1 safety)
- [ ] Hetzner account set up, payment method active, SSH keys uploaded
- [ ] Backblaze B2 account set up, bucket created, application key generated
- [ ] Cloudflare Workers Paid plan active (confirmed 2026-04-09) — repurposed for Load Balancer instead of R2 cache

---

## Notes on what is deliberately not in this plan

- **No R2 cache-fallback Worker.** ADR-003 rejected this as architecturally inferior to warm standby. The Cloudflare Workers Paid plan purchased on 2026-04-09 is still used, but for Load Balancer and future uses, not for R2 caching.
- **No 17-week v2 platform migration.** ADR-001 remains deferred. The concerns ADR-001 was meant to address (type safety, observability, testability) are addressed incrementally during the parameterization phases.
- **No SQLite-to-Postgres migration.** Tracked as a follow-up task, not a blocker. Rsync is sufficient for now.
- **No managed Postgres (Supabase, Neon).** Self-hosted saves $30-50/month and avoids vendor lock-in. Re-evaluated if ops burden becomes unmanageable.
- **No automation of Anders's review cycles.** Quality gates on new languages and verticals still require human spot-audits. Automation is not a goal — correctness is.

---

*End of Phase 0 — Cloud Migration and Expansion Acceleration Plan.*
