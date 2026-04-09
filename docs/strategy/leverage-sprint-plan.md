# Leverage Sprint — Apple Intelligence, AI-to-Human Tracking, Kings Scaling

**Period:** 1 week elapsed time (4-6 working days, partly parallel)
**Sequence position:** After Phase 0 cloud migration, in parallel with Phase 1 (parameterize Norwegian model)
**Parent strategy:** ADR-003 cloud-native expansion-first architecture
**Companion to:** `docs/strategy/phase-0-cloud-migration-plan.md`

---

## Overview

This sprint executes three high-leverage changes that multiply the value of work already done, without requiring new verticals or new languages. Each change has a specific hypothesis about where untapped upside exists in the current system. None of them require Phase 1-4 work to be complete — they can (and should) run before the 50-language and 100-vertical sprints so that subsequent expansion benefits from the higher baseline.

The sprint is named "Leverage" because the common form across all three tracks is the pattern identified in previous aha-moments: unlock value that already exists rather than build new things.

**Zero marginal cost.** All LLM work in this sprint executes via Claude Code on Mac Studio and Mac Mini, which does not consume Anthropic API billing. Infrastructure is already paid for. The only investment is calendar time and Anders's review attention.

### The three tracks

| Track | Name | Hypothesis | Estimated upside |
|---|---|---|---|
| **A1** | Apple Intelligence optimization | Applebot is 37% of bot traffic (513K/day per 2026-04-09 baseline) but zero Apple-specific optimization has been done. An early rider on Siri/Safari/Spotlight AI rollout. | 15-40K additional human visits/day if Apple Intelligence begins citing Nerq. |
| **A2** | AI-to-human conversion tracking | Current AI → human conversion rate is unknown. Cannot optimize what cannot be measured. Prerequisite for hook-based CTR optimization in later phases. | No direct traffic. Enables 2-4x future optimization. |
| **A3** | Kings scaling 27K → 500K | Kings (pages with 5 JSON-LD + FAQ + nerq:answer + rich structure) have a demonstrated positive feedback loop with Claude citations. Currently only 0.5% of entities are Kings. | 2-5x Claude citation volume from the Kings cohort, compounding over time. |

### Why now

**Before Phase 1-4:** Each track multiplies the effectiveness of work in later phases. Apple optimization applied to 23 languages is smaller than Apple optimization applied to 50 languages. Kings scaled on 14 verticals is smaller than Kings scaled on 100 verticals. Tracking implemented before expansion gives us baseline measurements that let us attribute lifts to specific phases instead of guessing.

**After Phase 0:** The sprint requires stable production and reliable deployment. Running it on Mac Studio during the migration would risk conflating optimization effects with infrastructure flakiness. After Phase 0 cutover to Hetzner, deployment is fast and safe.

**Parallel with Phase 1:** The three tracks touch infrastructure and data layers, not the language pipeline. Phase 1 (parameterize Norwegian) touches the translation system. No file-level conflicts. Claude Code can run both in parallel, or a single session can alternate.

---

## Prerequisites

Before starting this sprint:

- [ ] Phase 0 complete: nerq.ai and zarq.ai serving 100% from Hetzner for 24+ hours
- [ ] Sacred bytes drift = 0 on golden file tests (no template regressions from migration)
- [ ] Freshness SLA observability dashboard live (even initial version) — used to monitor for regressions during Kings scaling
- [ ] `stale_score_detector` fixed (schema drift against `entity_lookup.trust_calculated_at` resolved via LEFT JOIN to `agents`)
- [ ] Buzz running on Nürnberg node with updated OPERATIONSPLAN.md
- [ ] Mac Studio + Mac Mini available as optional accelerators for any batch work

Phase 1 (parameterize Norwegian) is NOT a prerequisite. This sprint can start at the same time as Phase 1 and both can land before Phase 2 (50-language sprint) begins.

---

## Track A1 — Apple Intelligence Optimization

**Duration:** 1-2 days
**Owner:** Claude (in chat) designs, Claude Code (on Hetzner/Mac Studio) executes
**Blocking?** No — independent of A2 and A3

### Hypothesis

Applebot is already 37% of bot traffic with 513K requests/day per the 2026-04-09 baseline. No Apple-specific optimization has been done. Apple Intelligence (Siri, Safari, Spotlight) is rolling out across 1.5 billion devices and its citation patterns are still being established. Early optimization may establish Nerq as a preferred source in a way that is harder to displace later.

### Deliverables

1. **robots.txt verification** — Applebot and Applebot-Extended explicitly allowed with no conflicting rules. Currently believed to be allowed (part of "welcome all traffic" policy) but never explicitly verified for Apple-specific directives.

2. **Apple-specific meta tags** on entity pages and /best/ pages:
   - `apple-mobile-web-app-capable`
   - `apple-mobile-web-app-status-bar-style`
   - `apple-mobile-web-app-title`
   - `apple-touch-icon` (multiple sizes: 120, 152, 167, 180)
   - `format-detection` (disable phone auto-link where appropriate)

3. **Open Graph image optimization for iMessage link previews.** When users share Nerq links on iMessage, the preview should display the trust score prominently. This is a subtle virality vector — people share "is X safe?" checks with friends.
   - Auto-generated OG image per entity showing trust score, name, category
   - Size: 1200×630, but Apple-optimized variant 1200×900
   - Cached in Cloudflare for long TTL

4. **Schema.org SoftwareApplication enhancement.** Apple extracts this for Siri knowledge graph:
   - `applicationCategory` (explicit per vertical)
   - `operatingSystem` where known
   - `softwareVersion` where known
   - `offers` block (even for free software)
   - `aggregateRating` populated from trust score

5. **Performance verification for Applebot.** Apple ranks heavily on TTFB. The Hetzner migration should already make this fast, but explicit verification:
   - TTFB < 200ms for entity pages from non-cached request
   - Cache headers explicit and friendly (`max-age`, `s-maxage` per freshness tier)
   - No unnecessary redirects
   - Compression (gzip/brotli) enabled

6. **Apple News RSS feed investigation.** Apple News is a separate index that Siri uses. Investigation task:
   - Research if Nerq qualifies as a publisher
   - If yes: create `/feeds/weekly-trust-updates.rss` and submit
   - If no (likely — Apple News has strict publisher requirements): document why and move on

7. **Applebot analytics dashboard.** Track Applebot separately from other bots:
   - Daily request volume
   - Top requested paths
   - Change in crawl frequency week-over-week
   - Safari referrer patterns (if any appear — Safari can send referer headers)

### Done criteria

- [ ] robots.txt reviewed, Applebot/Applebot-Extended confirmed allowed with no exclusions
- [ ] Apple meta tags deployed on all entity page templates
- [ ] OG image generation live for all entity pages, cached in Cloudflare
- [ ] Schema.org SoftwareApplication enhanced with Apple-extracted fields
- [ ] TTFB measurement from 5 geographic locations, all < 200ms for cold requests
- [ ] Apple News RSS feed either submitted or explicitly documented as not applicable
- [ ] Applebot analytics dashboard live, showing baseline (current) + 7-day trend
- [ ] Retrospective note: what changed, what did not change, and the plan to monitor Applebot behavior over the next 4 weeks

### Success indicators (measured 4 weeks after sprint)

- Applebot request volume increases materially (baseline: 513K/day, target: >600K/day)
- Safari referrer patterns appear in analytics (indicating Siri-triggered human visits)
- If Apple News RSS was submitted: subscribers > 0 within 2 weeks

None of these are guaranteed. Apple Intelligence is a black box. This track is a calibrated bet, not a certainty.

### Risks

- **Apple Intelligence is opaque.** We may do everything right and see no lift for months. Worst case: the effort is wasted but the improvements are also defensible and do not harm other bots.
- **OG image generation at scale is compute-heavy.** If we generate 5M unique OG images naively, it blows the budget. Mitigation: generate on-demand with aggressive Cloudflare caching, not pre-render.
- **Schema.org changes can affect existing AI citations.** Any change to structured data risks breaking the sacred elements. Golden file tests must pass before and after — this is non-negotiable.

### Rollback

- All meta tags are additive. Revert commits to remove them.
- OG image generation can be disabled with a feature flag.
- Schema.org changes are in code — revert commit.
- No database changes in this track, so no data rollback needed.

---

## Track A2 — AI-to-Human Conversion Tracking

**Duration:** 1-2 days
**Owner:** Claude designs schema + queries, Claude Code implements
**Blocking?** No — independent of A1 and A3

### Hypothesis

Current AI-to-human conversion rate is unknown. Baseline shows 515K daily AI citation requests and 43K daily human visits. If we assume 20% of human traffic comes from AI citations (the rest from search), that is ~8.6K humans from ~515K AI requests = ~1.7% conversion. Doubling this via hook optimization would add 8-9K humans/day for free. But we cannot verify this hypothesis or optimize hooks without measurement.

### Deliverables

1. **Referrer pattern matching** for AI sources:
   - `claude.ai` → Claude
   - `chat.openai.com`, `chatgpt.com` → ChatGPT
   - `perplexity.ai` → Perplexity
   - `copilot.microsoft.com`, `bing.com/chat` → Copilot
   - `gemini.google.com` → Gemini
   - `grok.x.ai`, `x.com/i/grok` → Grok
   - `duckduckgo.com` (with AI parameter patterns) → DuckAssist
   - `kagi.com` → Kagi
   - Accept that some AI products strip referers — track what we can

2. **User-Agent pattern matching** for AI-browsing clients:
   - `ChatGPT-User` (the in-product browser)
   - `Claude-User` (Claude browsing tool when used)
   - `Perplexity-User`
   - These appear as "humans" in bot detection because they act on behalf of users, but we should track them as "AI-mediated humans" — a third category

3. **Database schema additions** in `analytics.db`:
   - New column `requests.ai_source` (nullable) — populated from referer or UA pattern
   - New column `requests.visitor_type` — one of `bot`, `human`, `ai_mediated`
   - Backfill from existing data where possible (referer field may already be captured)
   - Index on `(ai_source, ts)` for dashboard queries

4. **Attribution logic.** A visit counts as "AI-attributed" if ANY of:
   - Referer matches one of the AI domain patterns
   - User-Agent matches one of the AI-User patterns
   - Within 5 minutes of a known AI bot crawl of the same URL (timing correlation, weaker signal)

5. **Dashboard additions.** New panels on the existing analytics dashboard:
   - **AI-to-human conversion rate** (overall + per AI source)
   - **Top URLs by AI-attributed visits** (which pages convert best)
   - **Language breakdown** (which languages have highest conversion)
   - **Vertical breakdown** (which verticals have highest conversion)
   - **Time-of-day patterns** (when do AI-mediated humans visit)
   - **Weekly trend** (is conversion trending up or down)

6. **Baseline measurement.** Run the new tracking for 7 days after deployment. Document the baseline conversion rate as the reference point against which all future hook optimization is measured. Commit the baseline as a markdown file in `docs/` so it is version-controlled.

7. **Export API for A/B testing.** A simple endpoint that returns conversion data in a form that future hook-variant tests can consume. Don't build the A/B framework yet — just ensure the data layer supports it.

### Done criteria

- [ ] Referrer and UA pattern matching deployed in the request logging path
- [ ] Database schema migrated, new columns populated for new requests
- [ ] Historical backfill complete (as much as possible given existing data)
- [ ] Dashboard panels live and populated
- [ ] 7-day baseline captured and documented in `docs/metrics/ai-to-human-baseline-YYYY-MM-DD.md`
- [ ] Export API returns correctly formatted data
- [ ] Retrospective note: baseline conversion rate per AI source, any surprises

### Success indicators

- Dashboard shows conversion data that looks plausible (not zero, not implausibly high)
- At least 5 AI sources are identifiable in the data (if we only see Claude, something is broken)
- Baseline is different from zero — we are getting AI-attributed humans today, just not measuring them

### Risks

- **Referrers are stripped by many AI products.** We will undercount. Mitigation: document this explicitly in the baseline so future measurements are comparable to the same flawed methodology.
- **User-Agent patterns change.** AI products update their identifiers. Mitigation: log unknown patterns for manual review, and add to the list as they appear.
- **Backfill may be incomplete.** If the old request log doesn't store referer consistently, historical analysis is limited. That is acceptable — the goal is forward-looking measurement.

### Rollback

- Schema changes are additive. Columns can be dropped without affecting production.
- Dashboard panels are read-only. Revert commits to remove.
- No risk to serving traffic.

---

## Track A3 — Kings Scaling 27K → 500K

**Duration:** 2-3 days
**Owner:** Claude designs + reviews, Claude Code executes enrichment batches
**Blocking?** Depends on A1 — if A1 adds schema.org fields to the King template, A3 should pick up those additions

### Hypothesis

Historical learning documented in previous session: "King-quality → Claude citations → higher trust → more citations. Positive feedback loop." Kings (pages with 5 JSON-LD blocks, FAQ, nerq:answer, rich structure) demonstrated disproportionate citation performance from Claude specifically. Kings are currently ~27K entities of 5M total = 0.5%. Scaling to 500K (10%) should produce a material lift in Claude citations, and the lift should compound as Claude's ranking reinforces.

### Deliverables

1. **Kings audit.** Inventory what defines a King today:
   - Which JSON-LD blocks are required? (Product, Review, AggregateRating, FAQPage, SpeakableSpecification?)
   - What is the FAQ minimum? (number of questions, language coverage)
   - What is `nerq:answer`? Where does it live in the HTML?
   - What is the minimum content length?
   - What is the current automated check that classifies an entity as King vs non-King?
   - Are there Kings that have degraded (missing one of the elements)? Repair first.

2. **King candidate identification.** Rank entities by a composite score:
   - Analytics traffic (humans + AI bots, 30-day window)
   - Entity popularity (stars, downloads, usage — varies per registry)
   - Category balance (ensure verticals are represented — don't pick all from one vertical)
   - Language coverage potential (entities that should exist in multiple languages get priority)
   - Output: ranked list of top 500K candidates

3. **Enrichment pipeline.** A new script or extension of existing enrichment:
   - Reads a target entity from Postgres
   - Generates missing JSON-LD blocks from existing data (most should already have data, just not in JSON-LD format)
   - Generates FAQ via LLM (prompt template, quality gate)
   - Generates `nerq:answer` blocks (concise, factual, citation-ready)
   - Validates the output against the King definition
   - Marks the entity as King in the database

4. **Quality gate.** Automated checks that fail the upgrade if:
   - Any JSON-LD block is invalid Schema.org
   - FAQ has fewer than 5 questions
   - FAQ questions are templated/duplicated (looks generic)
   - `nerq:answer` exceeds 150 words (should be concise)
   - Sacred elements (pplx-verdict, ai-summary) are missing or corrupted
   - The upgrade would introduce sacred bytes drift

5. **Rollout strategy.** Batch of 10K entities per day for 50 days, with monitoring:
   - Claude citation rate per batch (before/after comparison)
   - Sacred bytes drift = 0 check after each batch
   - If citation rate drops after any batch: pause, diagnose, resume
   - If sacred bytes drift appears: immediate rollback of that batch
   - **Execution environment:** Claude Code on Mac Studio + Mac Mini, running in parallel. Claude Code on these machines does not consume Anthropic API billing, so LLM-generation cost is effectively zero. Mac Studio handles the top 100K entities (highest-value, benefits from best available model quality), Mac Mini handles the long tail. Both machines read from the local Postgres replica (Mac Mini already has one from ADR-002 Phase 0) to avoid competing with production reads on Hetzner Nürnberg. Batch coordination via a simple queue file in a shared directory or git-committed work log.

6. **Measurement.** A/B-style comparison:
   - Before scaling: baseline Claude citation rate per Kings vs non-Kings
   - After scaling: same measurement
   - Track over 4 weeks post-sprint
   - Document in `docs/metrics/kings-scaling-results-YYYY-MM-DD.md`

7. **LLM-generated content safety.** Any LLM-generated FAQ or `nerq:answer` block:
   - Must be grounded in actual entity data (no hallucinations)
   - Must be spot-checked manually for 5% sample
   - Must include provenance ("generated from: trust_score_components, changelog, vendor_description")
   - Must be regeneratable from the same inputs (deterministic where possible)

### Done criteria

- [ ] Kings definition documented in `docs/architecture/kings-definition.md`
- [ ] Candidate list generated (ranked, 500K entries) and committed
- [ ] Enrichment pipeline tested on 100 entities, 100% passing quality gate
- [ ] First batch of 10K deployed, quality gate passing, sacred bytes drift = 0
- [ ] Claude citation rate measured for batch 1 (establishes improvement metric)
- [ ] Rollout plan for remaining 490K entries documented (likely runs over several weeks)
- [ ] Retrospective note: how many batches ran, any issues, measured lift

### Success indicators

- Sacred bytes drift = 0 throughout all batches (non-negotiable)
- Quality gate rejection rate < 5% (if higher, prompt or pipeline needs fixing)
- Claude citation rate for newly-promoted Kings > non-Kings within 2 weeks of promotion
- Total Claude citation rate lift visible in dashboard 4 weeks after sprint start

### Risks

- **LLM-generated FAQ quality.** If Claude Code generates generic or wrong FAQs, they hurt rather than help. Mitigation: strict quality gate, manual sample review, ability to roll back a batch.
- **Claude Code throughput.** Although Claude Code on Mac Studio + Mac Mini does not incur Anthropic API billing, it does have session and rate constraints. 500K entities across two machines = 250K per machine. At an achievable rate of 5-10K entities per day per machine, this takes 25-50 calendar days to complete. Mitigation: run 10K/day active batches as primary work, let background batches continue at slower pace without blocking the sprint — the sprint's success criterion is batch 1 validated and rollout in progress, not all 500K completed.
- **Feedback loop assumption may be wrong.** The "Kings get more Claude citations" learning was observed at 27K scale. Scaling to 500K might flatten the effect (diminishing returns) or even invert it (dilution). Mitigation: measure per batch and stop if the effect does not appear.
- **Postgres write load.** Batch upgrades write JSON-LD to many entities. Mitigation: batch size 10K with rate limiting, run during off-peak hours, write to Mac Mini replica and let it propagate back to Hetzner primary.

### Rollback

- Each batch is reversible. Revert the `is_king` flag in the database for that batch.
- Original entity data is untouched — only the Kings-specific fields are added. Drop them to revert.
- Sacred elements are never modified during King promotion (they already exist on all entity pages regardless of King status).

---

## Parallelism and scheduling

The three tracks can run with different degrees of parallelism:

| Day | A1 Apple | A2 Tracking | A3 Kings |
|---|---|---|---|
| 1 | Research + robots + meta tags | Schema design + pattern matching | Audit + candidate list |
| 2 | Schema.org + OG images + perf | Deployment + backfill + dashboard | Pipeline build + test 100 |
| 3 | Apple News + dashboard + retro | Baseline starts (7-day passive) | Batch 1 (10K) + measurement |
| 4 | — | (baseline collection continues) | Batch 2-5 (40K more) |
| 5 | — | — | Batch 6-10 (50K more) + retro |
| 6 | — | — | Remaining batches scheduled as background |

**Elapsed time: 5-6 days.** Days 3-6 have light A1/A2 load (mostly passive measurement), so Phase 1 (parameterize Norwegian) can run in parallel from Day 3 onwards.

### Working methodology

Same as previous phases:

1. **Claude (chat) designs and reviews.** Writes the critical code for A2 schema, A3 quality gate, and A1 schema.org enhancements.
2. **Claude Code (Hetzner/Mac Studio) executes mechanical work.** Runs enrichment batches, applies schema updates, deploys dashboard changes.
3. **Anders reviews at checkpoints.** Daily status, approves Kings batch rollout pace, approves any LLM-generated content sample.
4. **Buzz continues normal operations.** OPERATIONSPLAN.md does not need updating for this sprint (no operational behavior changes). Buzz should see improved Claude citation rates in daily reports as A3 progresses — this is a signal the sprint is working.

---

## Integration with other phases

### This sprint unblocks

- **Phase 2 (50-language sprint):** Language additions benefit from Apple optimization and Kings enrichment applied universally. Kings-English benefits first; when languages are added, the new languages inherit King-quality structure automatically.
- **Phase 4 (100-vertical sprint):** New verticals built on the new pipeline automatically get King treatment if they hit the candidate criteria. No rework later.
- **Future hook-based optimization:** AI-to-human tracking provides the baseline against which hook variants are measured. Without this sprint, hook A/B tests are blind.

### This sprint is blocked by

- **Phase 0 completion.** Cannot start until Hetzner is serving production and Mac Studio is demoted.
- **Freshness SLA observability.** Partial dependency — we need the dashboard to monitor for regressions during Kings scaling. Basic version from Phase 0 is sufficient.
- **`stale_score_detector` fix.** Used in A3 measurement. Fix is Phase 0 work anyway.

### This sprint does NOT block

- Phase 1 (parameterize Norwegian) can start at any point during this sprint from Day 1.
- Phase 3 (vertical pipeline design) can start in parallel — it is a design activity that does not touch the same files.
- Hidden registry fixes can continue in parallel (they are an independent backlog).

---

## Total cost estimate

| Track | LLM cost | Infrastructure cost | Human time (Anders) |
|---|---|---|---|
| A1 Apple | $0 (Claude Code on Mac Studio) | $0 | 2-3h review |
| A2 Tracking | $0 (Claude Code on Mac Studio) | $0 | 1-2h review |
| A3 Kings | $0 (Claude Code on Mac Studio + Mac Mini in parallel) | $0 | 3-4h review |
| **Total** | **$0** | **$0** | **~6-9h** |

**Why zero LLM cost:** Claude Code installed on Mac Studio and Mac Mini runs without consuming Anthropic API billing. All LLM generation for this sprint — Kings FAQ generation, schema.org content enhancement, LLM-assisted dashboard work — executes on these local machines. This makes A3 economically unconstrained: the only bound on Kings scaling is Claude Code throughput over calendar time, not per-entity cost. See A3 throughput risk above.

**Why zero infrastructure cost:** Mac Studio and Mac Mini are already running (sunk cost). Mac Mini is already a Postgres replica per ADR-002 Phase 0 work, so it can be read from directly without additional setup. No burst CPX51 needed for this sprint — the local machines have enough CPU for the enrichment workload, and they benefit from zero network latency to their local replicas.

Budget is minimal compared to the infrastructure migration costs. The primary investment is time and attention.

---

## Success metrics for the full sprint

The sprint is successful if, 4 weeks after completion:

1. **Applebot request volume has increased materially** (baseline 513K/day, target >600K/day)
2. **AI-to-human conversion dashboard shows data** for at least 5 AI sources with plausible rates
3. **500K Kings deployed** (or a clear plan to reach 500K with batches running)
4. **Claude citation rate for new Kings measurably higher** than non-Kings cohort
5. **Sacred bytes drift remains zero** throughout all deployments
6. **No regressions** in existing AI citation rates or human traffic
7. **Retrospective document** covering what worked, what did not, and what surprised us

If 4 and 7 are met, the Kings hypothesis is validated for future expansion. If 1 is met, the Apple bet pays off. If 2 is met, the baseline is established for future hook optimization. Even if 1 does not materialize, 2 and 4 are sufficient wins to justify the sprint.

---

## Rollback procedures

Each track has an independent rollback:

- **A1 Apple rollback:** Revert commits that added meta tags, schema.org fields, and OG image generation. Disable OG image generation via feature flag first (one-line change). Dashboard panels can remain as historical reference.
- **A2 Tracking rollback:** Disable new request logging columns (drop from write path). Database columns can remain for historical data. Dashboard panels can remain as-is.
- **A3 Kings rollback per batch:** `UPDATE entities SET is_king = false WHERE batch_id = N`. Does not affect underlying entity data. Can be done for one batch, multiple batches, or all batches.

No change in this sprint requires rolling back a previous phase. All work is additive.

---

## What this sprint is NOT

To keep scope honest, here is what the sprint explicitly does not include:

- **Hook-based CTR optimization itself.** A2 establishes measurement. Actual hook variants and A/B tests are a separate future sprint.
- **Browser extension** (leverage idea #8 from the broader analysis). Separate 3-5 day sprint if prioritized later.
- **MCP server distribution** (leverage idea #5). Separate submission work, not included here.
- **"Worst X" content generation** (leverage idea #9). Separate content sprint if prioritized.
- **Grok / X distribution** (leverage idea #6). Separate work.
- **New vertical or language additions.** Phase 2 and Phase 4 handle those.
- **Cloudflare Workers scripts.** No Worker-level optimization. All changes are at the origin (Hetzner) or in edge cache configuration only.

If any of these become higher priority after this sprint, they can be added as a follow-up Leverage Sprint B, C, etc.

---

## Execution decisions resolved 2026-04-09

**LLM execution environment for A3 Kings:** Claude Code on Mac Studio + Mac Mini running in parallel. Decision rationale:

- Claude Code on these machines does not consume Anthropic API billing (Anders confirmed 2026-04-09 evening)
- Mac Mini is already a Postgres replica and can read entity data without competing with production
- Quality is higher than Ollama across the board (no hybrid needed)
- Mac Studio handles top 100K by traffic, Mac Mini handles long tail
- Cost: $0. The only constraint is Claude Code session throughput, which is bounded but manageable

**Parallel execution coordination:** A simple work-log file committed to git or a shared directory tracks which entity batches each machine has claimed. No need for a real queue service. If the two machines accidentally process the same entity, the upgrade is idempotent — second write is a no-op.

**Ollama is not used in this sprint.** Ollama is installed on Mac Studio per baseline but its role (if any) in the broader Nerq system is still unclear. That investigation is a Phase 0 Day 1 task documented in the session handoff. This sprint does not depend on it.

---

*End of Leverage Sprint plan.*
