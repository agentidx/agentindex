# Leverage Sprint — Measurement-First Kings, AI-to-Human Tracking, Apple Intelligence

**Period:** Active phase approximately 5-7 sequential working sessions starting 2026-04-10, with background scaling continuing into Phase 0
**Sequence position:** Before Phase 0 cloud migration. Leverage Sprint runs first, then Phase 0, then Phases 1-4.
**Parent strategy:** ADR-003 cloud-native expansion-first architecture
**Sequence revision:** ADR-003 Addendum #3 (Leverage Sprint before Phase 0)
**Strategic pivot:** ADR-003 Addendum #4 (measurement-first Kings, hypothesis unverified) — this is the authoritative decision document for the A3 track structure
**Companion:** docs/strategy/phase-0-cloud-migration-plan.md (Phase 0-4 plan, still canonical, starts ~1 week after Leverage Sprint begins)

---

## Overview

This sprint executes three high-leverage tracks that aim to multiply the value of work already done, without requiring new verticals, new languages, or cloud infrastructure. Each track has a specific hypothesis. One of those hypotheses (Kings increase AI citations) was discovered during Day 1 audit to have never been measured in Nerq's codebase. The sprint has been restructured to measure before scaling.

Sprint started 2026-04-10, the day after the strategic planning session of 2026-04-09. Mac Mini was connected to Mac Studio the same day and has not yet run productive work. This sprint is the first productive use of that capacity.

The sprint is executed in sequential milestones, not fixed daily schedules. Anders works sequentially — some sessions complete 2 milestones, some sessions complete half of one. The milestones below are ordered by dependency, not by calendar.

**Zero marginal cost.** All LLM work in this sprint executes via Claude Code on Mac Studio and Mac Mini, which does not consume Anthropic API billing. Infrastructure is already paid for. The only investment is calendar time and Anders's review attention.

### The three tracks

**A1 Apple Intelligence optimization.** Applebot is 37% of bot traffic (513K requests/day per the 2026-04-09 baseline) but zero Apple-specific optimization has been done. Bet on early rider status as Siri, Safari, and Spotlight AI rollouts establish citation patterns.

**A2 AI-to-human conversion tracking.** Current AI-to-human conversion rate is unknown. Baseline shows 515K daily AI citation requests and 43K daily human visits. Cannot optimize what cannot be measured. Prerequisite for hook-based CTR optimization in later phases and for A3 measurement.

**A3 Kings — four phases in sequence.** Kings are a set of entity pages with enhanced structured data. Current count: 37,688 across 26 registries. Of these, 81% are at king_version=0 (never enriched beyond initial seed), 99.3% lack populated dimensions data, 225 have broken or missing descriptions, all 158 country Kings share trust score 48.2 (likely a bug). The hypothesis that Kings receive more AI citations than non-Kings has never been measured — confirmed by audit of flywheel_dashboard.py and citation_tracker.py on Day 1. A3 is restructured as Measure, Fix, Gate, Scale, with scaling gated on measurement results. 500K remains the ambition if the hypothesis holds.

### Why now (sequence rationale unchanged from Addendum #3)

Mac Mini is idle capacity already paid for, connected 2026-04-09. Mac Studio's acute risks are mitigated (autoheal loop fixed, remaining risks are accepted hardware-failure probabilities). Momentum compounds; pauses do not. Leverage Sprint improves Phase 0 readiness by establishing measurement infrastructure (A2) and stress-testing Mac Mini under real load (A3 validation work) before the cloud migration depends on those capabilities.

### What changed on Day 1 (2026-04-10)

Day 1 was audit and documentation only. The following facts were established and affect sprint execution:

1. Backup of current production state was completed and verified at ~/nerq-backups/2026-04-10-pre-leverage-sprint. Total 14 GB across Postgres dump, SQLite copies, sacred HTML snapshots, and git state.

2. Ollama discovery: Buzz runs entirely on local Ollama qwen3:8b which is documented as insufficient for her workload. This is not a Leverage Sprint blocker but is a Phase 0 blocker. See docs/status/2026-04-10-ollama-buzz-discovery.md. Decision for the sprint: leave Buzz running as-is, do not touch her, she will remain in a degraded-but-contained state for the duration of the sprint.

3. Kings audit revealed the architecture has no central classification function, most Kings have never been enriched, and the Kings to AI citations hypothesis has never been measured. See docs/architecture/kings-definition.md and ADR-003 Addendum #4 for full details.

4. Autovacuum has never run on agents, entity_lookup, or agent_jurisdiction_status tables. Statistics are stale. Not blocking, but ANALYZE should be run on these tables at some point during or after the sprint to refresh statistics.

## Prerequisites

All prerequisites for starting the sprint have been met as of Day 1 completion:

- Mac Studio healthy, uptime stable, no active autoheal incidents
- Mac Mini connected, reachable via Tailscale at 100.115.230.106, Postgres replica live
- Claude Code installed and working on both machines
- Working tree clean, main branch, HEAD at cf4df28 or later
- Baseline capture from 2026-04-09 intact at ~/nerq-baselines/2026-04-09-pre-migration/
- Pre-sprint backup from 2026-04-10 complete at ~/nerq-backups/2026-04-10-pre-leverage-sprint/
- ADR-003 Addendum #4 committed as authoritative decision source for A3 track
- kings-definition.md audit document in place (with known corrections pending — see milestone M2 below)

## Milestones

The sprint progresses through numbered milestones in rough dependency order. Each milestone has a checkpoint where Anders and Claude session review before moving to the next. Milestones do not map 1:1 to calendar days.

**M1 — Day 1 audit and pivot documentation (COMPLETED 2026-04-10 morning).**
Deliverables: pre-sprint backup, Ollama discovery document, kings-definition.md audit, ADR-003 Addendum #4 strategic pivot, this rewritten leverage-sprint-plan.md. Status: complete. Next commit includes all Day 1 outputs.

**M2 — kings-definition.md corrections.**
Fix two audit errors (wrong file paths for android_play_crawler.py and agent_safety_page.html, truncated registry list missing 6 registries totaling 597 Kings). Add a section explicitly stating the Kings-to-citations hypothesis is unmeasured per ADR-003 Addendum #4. Estimated effort: 15-30 minutes. Blocker: none. Runs as a patch operation on existing file.

**M3 — A2 schema design and deployment.**
Extend analytics.db requests table with ai_source (nullable text) and visitor_type (text with constraint bot/human/ai_mediated). Add index on (ai_source, ts). Deploy referer pattern matching and user-agent pattern matching for known AI sources (Claude, ChatGPT, Perplexity, Copilot, Gemini, Grok, DuckAssist, Kagi) and AI-User clients (ChatGPT-User, Claude-User, Perplexity-User). Backfill historical rows where referer data exists. Deploy dashboard panels showing conversion rate per AI source, top URLs by AI-attributed visits, language/vertical breakdowns, 7-day trends. M3 runs on Mac Studio. Mac Mini runs read-only backfill queries from analytics.db replica if set up — otherwise backfill happens on Mac Studio too.

**M4a — A1 Apple Intelligence quick wins (COMPLETED 2026-04-10 afternoon).**
Deployed scope: Apple meta tags on English entity pages (agent_safety_page.html), Schema.org SoftwareApplication enhancements (offers, license, datePublished, image) on entity pages, robots.txt max-snippet:-1 directives for Applebot and Applebot-Extended on both Nerq and ZARQ hosts, broken og:image on homepage template fixed (was pointing to non-existent og-nerq.png, now nerq-logo-512.png), ZARQ section of robots.txt got its missing Applebot and Applebot-Extended directives added.

Deployment verified via curl against production (post-Cloudflare-purge). Sacred bytes intact on all entity pages (pplx-verdict, ai-summary, SpeakableSpecification counts preserved).

Audit revealed scope gaps that became M4b. Specifically:
1. Localized routes (/sv/, /de/, /ja/, /no/, and 19 other language variants) do not use the patched agent_safety_page.html template directly. They go through agentindex/localized_routes.py post-processing which has its own rendering path.
2. Root homepage / is served by ab_test.py render_homepage() with 4 A/B variants, not by homepage_i18n.py.
3. agent_safety_pages.py SoftwareApplication JSON-LD generation needed explicit fields added (done). But localized entity pages may need their own JSON-LD adjustments depending on how localized_routes rewrites them.

Audit file: docs/status/leverage-sprint-day-2-a1-apple-research.md

**M4b — A1 Apple Intelligence extended coverage (LARGELY COMPLETED 2026-04-10 afternoon).**
Execution target: start directly after M4a is committed, runs as next milestone after M5 (A3-Measure) or interleaved with A3-Fix if time permits. Not a future sprint — part of this sprint.

M4b deliverables:

1. Apple meta tags on all 23 language variants of the homepage and entity pages. This requires patching agentindex/localized_routes.py which post-processes language variants. Likely also requires understanding how that file interacts with homepage_i18n.py render_localized_homepage (our M4a patch on that file took effect for the base template but not the post-processed output).

2. Apple meta tags on all 4 A/B variants of the root homepage /. This requires patching agentindex/ab_test.py render_homepage(). Must preserve A/B test tracking — any patch here must be audited carefully so analytics attribution is not broken.

3. Open Graph image generator. On-demand per-entity PNG at /og/{slug}.png rendered by Pillow, cached by Cloudflare for 7 days, using trust score + entity name + category as card layout. Must respect Mac Studio memory pressure (currently 95% RAM). Fallback: if Pillow generation is too heavy, serve a single static card per trust grade (A+, A, B, C, D, F).

4. Apple touch icons at 4 sizes (120, 152, 167, 180) generated from nerq-logo-512.png. Either pre-generate at build time to static files, or serve on-demand via the same mechanism as OG images.

5. ETag header support in Redis cache middleware (discovery.py around line 266-300). Compute ETag from Redis cache key + content hash. Handle If-None-Match conditional requests to return 304. Enables Applebot efficient re-crawl.

6. Applebot analytics panel in agentindex/flywheel_dashboard.py. Daily request volume trend, top paths requested, percentage of bot traffic, Safari referer patterns if any appear.

7. Investigate the max-age=14400 discrepancy (live response shows 14400, code sets 300). Understand whether Cloudflare is rewriting or an intermediary is involved. Not blocking but affects cache expectations.

8. Remove duplicate index idx_ts on analytics.db. idx_requests_ts and idx_ts both index the ts column alone — one is redundant. Minor cleanup flagged by M3 audit.

M4b risks:
- localized_routes.py is 12,261 lines. Patch must be surgical, not a rewrite.
- ab_test.py patch risks breaking A/B tracking if not careful.
- OG image generation at 5M+ entities scale needs capacity validation before full rollout.
- Sacred bytes drift = 0 must be preserved across all localized variants, not just English.

M4b runs on Mac Studio primarily. Mac Mini can run TTFB measurements against a sample of localized URLs to verify parity with English pages after deployment.

**M4b completed in this sprint (2026-04-10):**
- Step 1: _render_localized_page_minimal fallback patch (localized_routes.py)
- Step 2: ab_test.py _HEAD patch (root / + all 4 A/B variants)
- Step 3a: Apple touch-icon generation (120, 152, 167, 180)
- Step 3b: Template sized-icon updates (agent_safety_page.html, homepage_i18n.py)
- Step 5: ETag support in PageCacheMiddleware (discovery.py)
- Step 6: Applebot in bot summary bar (flywheel_dashboard.py)
- Step 7: max-age discrepancy documented (discovery.py comment)
- Step 8: Duplicate index cleanup (DROP INDEX idx_requests_ts, 582 MB recovered)

**M4b deferred to M4c (follow-up milestone):**
- Step 4: OG image generator — on-demand Pillow with Cloudflare caching
  OR fallback plan with 10 static grade PNGs + entity template integration.
  Not generated today because template integration requires grade mapping
  at render time and deserves its own commit cycle.

**M4c — A1 Apple Intelligence visual differentiation and classification.**
Follow-up milestone for work identified during M4b but deferred for
scope and safety. Target: run after M5 (A3-Measure) completes, or
interleaved with Day 3 work.

M4c deliverables:

1. OG image generator. Choose between per-entity dynamic Pillow
   generation (preferred if Mac Studio memory allows) or 10 static
   grade PNGs (safer fallback). Per-entity design is in
   docs/status/leverage-sprint-day-2-m4b-audit.md Step 4. Includes
   route /og/{slug}.png, template updates, Cloudflare 7-day cache,
   memory monitoring.

2. Apple touch-icon size variants as standalone files. Currently
   M4b batch 1 generated 4 PNGs pointing from all templates, but
   nothing special per-context. M4c may want high-res source
   (1024px) pre-generated if we ever need apple-touch-icon-precomposed.

3. Applebot reclassification from search bot to AI Indexing. Currently
   bot_name='Apple' has is_ai_bot=0 (search bot category) which
   excludes it from both AI Citations and AI Indexing dashboard cards.
   Given Applebot powers Apple Intelligence (Siri, Spotlight, Safari
   Suggestions), it should be reclassified as is_ai_bot=1 and added
   to the AI Indexing SQL filter in flywheel_dashboard.py alongside
   GPTBot. Scope: analytics.py bot mapping, backfill of ~1.5M existing
   rows, flywheel_dashboard.py query updates, cache regeneration.
   Risk: retroactive dashboard semantic change, historical charts will
   show different numbers. Priority: lower than M5 but should be
   resolved before any stakeholder reporting.

## M4b Open Questions (carried forward)

1. **Cloudflare Browser Cache TTL (resolved):** Accept as-is. 14400s
   (4h) browser cache is reasonable for a site where trust scores
   change daily. Code's max-age=300 is effectively dead code and is
   now documented as such in discovery.py:263.

2. **OG image fonts:** DM Serif Display and DM Sans not installed.
   M4c decision: download to static/fonts/ for branded cards, or
   use system Helvetica as default.

3. **OG image strategy:** Fallback plan (10 static grade images) is
   safer for Mac Studio memory pressure but less differentiated.
   Per-entity dynamic generation is more valuable for social sharing
   but requires capacity validation. M4c decision.

4. **Applebot classification:** Reclassify as AI Indexing (see M4c
   deliverable 3). Not done in M4b because retroactive dashboard
   semantic change deserves its own commit cycle and deeper audit
   of all is_ai_bot=1 queries in flywheel_dashboard.py.

5. **VACUUM timing:** Not performed. DROP INDEX idx_requests_ts was
   sufficient; SQLite reuses freed pages naturally.

6. **Redis cache flush after deploy:** Performed via Python-based
   iteration (17,062 pc:* keys deleted) — xargs failed on keys with
   quoted characters. Python redis-py library handles binary safely.

**M5 — A3-Measure built on top of A2 infrastructure.**
Extend citation_tracker.py or flywheel_dashboard.py with a Kings vs non-Kings split. Produce query output showing: AI bot crawl rate per page per day for Kings, same for non-Kings, broken down by bot source (ClaudeBot, GPTBot, PerplexityBot, Applebot, others), AI-attributed human visits per Kings vs non-Kings page once A2 is live. The panel or query should produce a simple numerical comparison that can be read at a glance. M5 depends on M3 (A2) being at least partially complete so the ai_source column exists. M5 runs on Mac Studio.

**M6 — A3-Fix runs on Mac Studio while Mac Mini validates in parallel.**
Mac Studio writes repairs to primary Postgres throttled to approximately 100 updates per second to protect serving capacity. Mac Mini reads from replica and fetches production URLs to run an HTML-level validator: does the page render the 5 king_sections correctly, is the ItemList JSON-LD present when is_king is true, is the nerq:answer meta tag populated, are the sacred elements intact. Mac Mini output is a report of Kings that are database-marked as is_king=true but HTML-degraded. Mac Studio fix categories: 225 Kings with broken descriptions, 28 Kings with trust_score below 30 (decision per entity: fix score or demote), country Kings bug (all 158 at 48.2 — investigate and either fix or document as limitation), dimensions column populated where underlying data exists. Deliverable: scripts/validate_kings.py as reproducible validator, a report of fix outcomes, and a count of how many Kings now pass full validation.

**M7 — A3-Gate central promote_to_king() function.**
Single function with explicit, auditable rules derived from the validator built in M6. Takes an entity ID and a reason string, validates that the entity meets central Kings criteria, either promotes or rejects with a logged reason. Unit tests covering edge cases. Not wired into existing crawlers yet — they continue to use their independent logic. Future sprint will migrate crawlers to the central function. M7 output: the function, its tests, a one-page ADR snippet describing the rules as authoritative source.

**Decision checkpoint (after M5 has collected ~5-7 days of data):**
Review A3-Measure data. If Kings show materially higher AI bot crawl rates or higher AI-attributed human traffic than comparable non-Kings, A3-Scale proceeds. If the data is ambiguous or shows no difference, wait longer — even if it costs coordination overhead with Phase 0. Statistical sufficiency matters more than the schedule. Anders makes this call with data in hand, not Claude Code autonomously.

**M8 — A3-Scale, gated on decision checkpoint.**
If decision is go: Mac Mini takes the A3-Scale worker role. She calls promote_to_king() via Tailscale against primary Postgres in aggressive parallelism. Target: 500K Kings as the original ambition. Rate: start conservative (~5K per day), scale up based on Mac Studio load, Postgres pool health, and Mac Mini's own capacity. Stress test Mac Mini in the process — push until we find her ceiling. This is secondary goal data for Phase 0 planning. Runs in background for weeks, coordinating with Phase 0 cutover (pause during pg_dump, pause during cutover, resume after). If decision is wait or no-go: M8 does not start, sprint ends after M7, resources redirect to deeper A1 or A2 work.


## Track A1 — Apple Intelligence optimization details

**Hypothesis:** Applebot is already 37% of bot traffic per the 2026-04-09 baseline. No Apple-specific optimization has been done. Apple Intelligence is rolling out across ~1.5 billion devices and its citation patterns are still being established. Early optimization may establish Nerq as a preferred source in a way that is harder to displace later.

**Deliverables:**

1. robots.txt verification that Applebot and Applebot-Extended are explicitly allowed with no conflicting rules.

2. Apple-specific meta tags on entity pages and /best/ pages: apple-mobile-web-app-capable, apple-mobile-web-app-status-bar-style, apple-mobile-web-app-title, apple-touch-icon in sizes 120 180 152 167, format-detection.

3. Open Graph image generation for iMessage link previews, on-demand with aggressive Cloudflare caching. Size 1200x630 standard plus 1200x900 Apple-optimized variant. Generated from trust score, entity name, category. Same render-on-demand pattern as ADR-003.

4. Schema.org SoftwareApplication enhancements: applicationCategory explicit per vertical, operatingSystem where known, softwareVersion where known, offers block even for free software, aggregateRating populated from trust score.

5. Performance improvements Applebot responds to: cache headers explicit with max-age and s-maxage, no unnecessary redirects, gzip and brotli compression verified. Mac Studio TTFB may remain above Apple preferred threshold regardless — document the number, accept that Phase 0 cloud migration addresses it further.

6. Apple News RSS feed investigation. Submit to Apple News if Nerq qualifies as publisher. If not (Apple News has strict publisher requirements), document why and move on. Do not fake publisher status.

7. Applebot analytics panel in the existing flywheel or analytics dashboard. Daily request volume, top requested paths, week-over-week crawl frequency change, Safari referrer patterns if any appear.

**Done criteria:** robots.txt verified, meta tags deployed and rendering in production, OG image generation live and Cloudflare-cached, Schema.org enhancements in place without sacred bytes drift, TTFB measurements captured from Mac Studio and Mac Mini as two vantage points, Apple News RSS submitted or documented as inapplicable, analytics panel live with baseline plus 7-day trend.

**Success indicators (measured 4 weeks after sprint):** Applebot request volume increases above baseline 513K per day, Safari referrer patterns appear in human traffic, Apple News subscribers above zero if submitted. None are guaranteed. Apple Intelligence is a black box. This track is a calibrated bet.

**Risks:** Opaque Apple Intelligence means we may do everything right and see nothing for months. Mitigation: improvements are defensible regardless of Apple response. OG image generation at scale could consume compute — mitigation is on-demand with Cloudflare caching, not pre-render. Schema.org changes risk breaking sacred elements — golden file tests must pass before and after.

**Rollback:** All meta tags are additive, revert commits to remove. OG image generation behind a feature flag. Schema.org changes in code, revertible. No database changes.

## Track A2 — AI-to-human conversion tracking details

**Hypothesis:** Current AI-to-human conversion rate is unknown. Baseline shows roughly 515K daily AI citation requests and 43K daily human visits. If 20% of human traffic comes from AI citations (assumption), that is about 8.6K humans from 515K AI requests equal to ~1.7% conversion. Doubling this via hook optimization would add 8-9K humans per day. But we cannot optimize without measurement. A2 also provides the infrastructure that A3-Measure depends on.

**Deliverables:**

1. Referer pattern matching for AI sources: claude.ai to Claude, chat.openai.com and chatgpt.com to ChatGPT, perplexity.ai to Perplexity, copilot.microsoft.com and bing.com/chat to Copilot, gemini.google.com to Gemini, grok.x.ai and x.com/i/grok to Grok, duckduckgo.com with AI parameters to DuckAssist, kagi.com to Kagi. Accept that some AI products strip referers — track what we can.

2. User-Agent pattern matching for AI-browsing clients: ChatGPT-User, Claude-User, Perplexity-User. These appear as humans in bot detection but are tracked as a third category ai_mediated.

3. Database schema additions in analytics.db requests table: ai_source nullable text column, visitor_type text column with constraint of bot, human, or ai_mediated. Index on (ai_source, ts). Backfill from existing data where referer was already captured.

4. Attribution logic. A visit counts as AI-attributed if ANY of: referer matches AI domain patterns, user-agent matches AI-User patterns, or within 5 minutes of a known AI bot crawl of the same URL (timing correlation, weaker signal).

5. Dashboard additions: conversion rate overall and per AI source, top URLs by AI-attributed visits, language breakdown, vertical breakdown, time-of-day patterns, weekly trend.

6. Baseline measurement document written after 7 days of tracking as reference point for future comparison. Committed to docs/metrics/ai-to-human-baseline-2026-04-17.md or similar dated filename.

7. Export API endpoint returning conversion data in a stable format for future A/B testing of hook variants.

**Done criteria:** Pattern matching deployed in request logging path, schema migrated and new columns populated for new requests, backfill complete where possible, dashboard panels live and populated with plausible data for at least 5 AI sources, baseline measurement initiated.

**Success indicators:** Dashboard shows non-zero conversion data that looks plausible, at least 5 AI sources identifiable, baseline differs from zero (we are getting AI-attributed humans, just not measuring them before this track).

**Risks:** AI products strip referers and we will undercount — document methodology so future measurements are comparable to the same flawed methodology. User-Agent patterns change over time — log unknown patterns for manual review. Backfill may be incomplete if old logs do not store referer consistently.

**Rollback:** Schema changes are additive, columns can be dropped without affecting production. Dashboard panels are read-only. No risk to serving traffic.

## Track A3 — Kings in four phases details

Four phases executed in sequence. Each phase has its own deliverables, done criteria, and risks. The sequence is Measure, Fix, Gate, Scale. A3-Scale is gated on A3-Measure results per ADR-003 Addendum #4.

### A3-Measure (highest priority within A3)

**Purpose:** Test the hypothesis that Kings receive more AI citations than non-Kings before investing in scaling.

**Deliverables:** Extension to citation_tracker.py or a new query in flywheel_dashboard.py producing Kings vs non-Kings split of AI bot crawl rate per page per day, broken down by bot source (ClaudeBot, GPTBot, PerplexityBot, Applebot, others), plus AI-attributed human visits per page per day for Kings vs non-Kings once A2 data is flowing. Output is a numerical comparison that Anders and Claude session can read at a glance and judge.

**Methodology note:** The comparison must be per page, not total. Kings are a small percentage of total indexable pages, so total counts favor non-Kings trivially. The measurement is about yield per page. Kings versus a matched sample of non-Kings in the same registries and trust score ranges would be ideal if feasible.

**Done criteria:** Measurement query or panel is live and producing data. Data is collected for at least 5-7 days before any scaling decision. The measurement is reproducible on demand.

**Decision trigger:** After 5-7 days of collected data, review. If Kings show materially higher AI bot crawls or higher AI-attributed traffic per page than non-Kings, A3-Scale gets go-ahead. If the data is tight, ambiguous, or shows no difference, wait for more data even if it costs Phase 0 coordination overhead. Statistical sufficiency matters more than schedule.

### A3-Fix

**Purpose:** Repair the 37,688 existing Kings to meet defined quality before any scaling. Fixing is worthwhile independent of the hypothesis because it improves content quality universally.

**Deliverables:**

1. Zero Kings with NULL, empty, or sub-10-character descriptions. Currently 225. Repair the description or demote to non-King if the underlying data is truly missing.

2. Zero Kings with trust_score below 30. Currently 28. Either fix the score via re-scoring or demote. Per-entity decision.

3. Country Kings scoring bug investigation. All 158 countries share trust_score 48.2 which is almost certainly a bug. Either fix the scoring function or document as known limitation and demote countries from King status until fixable.

4. Dimensions column populated for as many Kings as possible. Currently only 275 of 37,688 (0.7%). If the underlying dimension data exists elsewhere in the database, populate. If it does not exist for certain registries, accept lower coverage and document which registries cannot be fully populated.

5. scripts/validate_kings.py as reproducible validator that checks each King against the full quality bar and reports failures by category. Can be run ad hoc after the sprint and during Phase 0 to verify no regressions.

6. HTML-level validation report from Mac Mini listing Kings that are database-marked is_king=true but whose rendered HTML is missing king_sections, the ItemList JSON-LD, the nerq:answer meta tag, or sacred elements.

**Done criteria:** All four numeric targets hit (or documented as unachievable with reason). Validator script committed and run successfully against full Kings set. HTML-level report reviewed, any HTML-level failures fixed.

**Throttling:** All writes to primary Postgres throttled to approximately 100 row updates per second to protect serving capacity. If A3-Fix takes 6 hours instead of 1 hour because of throttling, that is the correct trade.

**Compute split:** Mac Studio writes fixes. Mac Mini reads from replica and fetches production URLs to run validator in parallel. Mac Mini does not write to primary during A3-Fix.

### A3-Gate

**Purpose:** Build the central promote_to_king function that replaces scattered per-crawler logic. Future promotions go through this function. Existing crawlers are not migrated in this sprint — that is a follow-up task.

**Deliverables:**

1. promote_to_king(entity_id, reason) function that validates entity against central Kings criteria (derived from A3-Fix validator) and either promotes or rejects with logged reason.

2. Unit tests covering edge cases: already-King entity, entity missing required fields, entity with borderline trust score, entity in registry with special rules.

3. Documentation snippet added to docs/architecture/kings-definition.md or a new docs/architecture/kings-gate.md describing the rules as authoritative source.

4. Audit log table or extension to existing logs recording every promotion and rejection decision with timestamp and reason string.

**Done criteria:** Function committed with tests passing. Documentation reflects the rules. Dry-run test against a sample of existing Kings verifies the function would accept most and identifies any it would reject (informative audit).

**Not in scope for this sprint:** Migrating existing crawlers to use promote_to_king. They keep their independent logic. Only new promotions via A3-Scale use the function.

### A3-Scale (gated, conditional on A3-Measure decision checkpoint)

**Purpose:** If A3-Measure validates the hypothesis, systematically scale Kings toward the 500K ambition using the A3-Gate function. Mac Mini is the primary worker for this phase.

**Deliverables (only if decision checkpoint is go):**

1. Candidate selection query that ranks non-King entities by a composite score across analytics traffic, entity popularity, category coverage, and language potential. Output: ranked list of candidates committed to docs/metrics/kings-candidates-YYYY-MM-DD.csv.

2. Mac Mini worker script that reads candidates, calls promote_to_king via Tailscale against Mac Studio primary, logs results. Respects a work-log file to enable pause and resume. Coordinates with Phase 0 via pause signals.

3. Monitoring: Claude citation rate per batch measured via A3-Measure panel. Sacred bytes drift = 0 check after every batch via golden file tests. Mac Studio Postgres pool health monitored — if pool exhaustion approaches, throttle Mac Mini worker.

4. Stress test data: Mac Mini CPU, RAM, network, and Postgres client connection observations documented as secondary output. This data feeds Phase 0 planning about Mac Mini's capacity in its future role.

**Rate:** Start conservative at about 5K promotions per day. Scale up based on Mac Studio load and Mac Mini ceiling. No hard upper bound on parallelism from Mac Mini — we are explicitly trying to find her ceiling.

**Pause rules:** Mac Mini worker pauses during Phase 0 pg_dump (estimated 30 minutes), during Postgres transfer (estimated 8-14 hours), during cutover (estimated 24 hours). Resumes after each phase from the work-log position.

**Target:** 500K Kings as the original ambition. Reaching 500K is not the sprint success criterion — running the scaling with measurement oversight is.

**Done criteria (active sprint phase):** Candidate list generated, Mac Mini worker deployed and running, first 10K promotions completed with zero sacred bytes drift, A3-Measure data updated to show post-scaling effect, Mac Mini capacity observations logged.

**Done criteria (background phase after active sprint ends):** Scaling continues into Phase 0 background with pause coordination. Reaches 500K when it reaches it, or stops earlier if A3-Measure data shows the effect reversing or flattening.

## Compute allocation

**Mac Studio (primary, production server, write authority):**

- All A1 Apple deliverables (production code deploy)
- All A2 deliverables (schema migration on analytics.db, which lives only on Mac Studio)
- A3-Measure query development and deployment (reads analytics.db + Postgres, writes to dashboard)
- A3-Fix writes to primary Postgres, throttled to ~100 updates per second
- A3-Gate function development and testing
- Serving production traffic (unchanged)
- Buzz running in her degraded state (unchanged, do not touch)

**Mac Mini (replica, aggressive utilization, read-heavy first then write-worker for A3-Scale):**

Phase 1 (during A3-Measure and A3-Fix):
- HTML-level validator running against production URLs for every Kings entity
- TTFB measurements for A1 against 10K entity URLs as second vantage point
- A2 backfill queries reading from analytics.db if replication exists, otherwise standby
- Stress test: push her hard, record CPU, RAM, network, disk, Postgres client load, find the ceiling

Phase 2 (during A3-Scale, gated on measurement checkpoint):
- Primary A3-Scale worker. Calls promote_to_king() via Tailscale against Mac Studio primary.
- Aggressive parallelism — as many concurrent promotions as she can handle without saturating Mac Studio Postgres pool.
- Continues stress test observations — this data informs Phase 0 planning.

Mac Mini does NOT: run the A3-Gate function definition, promote Kings using logic other than calling the central function, modify OPERATIONSPLAN.md, touch Buzz, serve production traffic.

**Why asymmetric:** Mac Studio is load-sensitive (serving production, 95% RAM pressure, running Buzz). Mac Mini has no other responsibilities. We push Mac Mini hard to learn her ceiling and to use capacity that would otherwise sit idle. We protect Mac Studio carefully.

## Coordination with Phase 0

Phase 0 cloud migration starts approximately 2026-04-15, which is during or after the active phase of Leverage Sprint depending on Anders's pace. Coordination rules:

**Before Phase 0 starts:** Leverage Sprint A1, A2, A3-Measure, A3-Fix, A3-Gate are active on Mac Studio and Mac Mini without Phase 0 interference.

**During Phase 0 provisioning (Week 1 of Phase 0):** Mac Studio is busy with Hetzner provisioning and Postgres preparation. Mac Studio Leverage Sprint work slows or pauses. Mac Mini continues.

**During pg_dump (estimated 30 minutes):** Both machines pause writes to primary Postgres. Mac Mini A3-Scale worker pauses via work-log pause signal. Mac Studio A3-Fix pauses.

**During Postgres transfer (estimated 8-14 hours):** Both machines paused on writes. Mac Mini can continue validator reads and TTFB measurements (read-only). Mac Studio continues serving traffic unchanged.

**During cutover (estimated 24 hours):** Full pause on Leverage Sprint write activity. Sacred bytes drift verification via golden file tests runs on the new Hetzner primary before Mac Mini A3-Scale worker is allowed to resume.

**After cutover (Hetzner is primary):** Mac Mini A3-Scale worker resumes, now writing to Hetzner primary via Tailscale instead of Mac Studio primary. Work-log picks up from last position. Mac Studio can continue as Leverage Sprint accelerator or be repurposed, depending on what Phase 0 decides for its role.

## Success criteria

Sprint is successful if the following hold at end of active phase (regardless of A3-Scale decision):

1. Pre-sprint backup was taken and verified. (Already done on Day 1.)
2. Ollama-Buzz discovery documented and not acted on prematurely. (Already done.)
3. kings-definition.md audit document committed with corrections applied.
4. ADR-003 Addendum #4 committed as authoritative source for A3 structure.
5. A2 AI-to-human conversion tracking deployed, producing data for at least 5 AI sources.
6. A1 Apple optimization deployed: meta tags live, OG image generation active, Schema.org enhanced, analytics panel showing Applebot separately.
7. A3-Measure query or panel built and collecting data.
8. A3-Fix completed or explicitly deferred for specific items with documented reasons. scripts/validate_kings.py committed.
9. A3-Gate promote_to_king() function committed with tests.
10. Mac Mini stress test data collected: observed ceiling for sustained read workload, observed ceiling for any write workload that happens during A3-Scale.
11. Decision checkpoint on A3-Scale reached with explicit documented decision (go, wait, or no-go).
12. Sacred bytes drift = 0 throughout all deployments.
13. No regressions in existing AI citation rates or human traffic.
14. Retrospective document covering what worked, what did not, what surprised us.

If criteria 11 results in go, A3-Scale runs in background and the 500K target is pursued. If criteria 11 results in wait, measurement continues and go decision is deferred. If criteria 11 results in no-go, sprint ends at M7 and resources redirect per ADR-003 Addendum #4.

## Risks

**Top risk: Kings hypothesis might not hold.** A3-Measure exists specifically to test this risk. Cost of discovering "Kings do not outperform non-Kings" is the A3-Measure and A3-Fix investment, which is recoverable regardless (fixes improve quality, measurement infrastructure is reused for hooks).

**Mac Studio hardware failure during sprint.** 2-5% per week. Loss: work in progress. Backup taken on Day 1 mitigates data loss. Time loss is unrecoverable.

**Mac Mini instability under first real load.** She has not run production work. Mitigation: start at moderate load for stress test, scale up gradually, monitor. A crash is acceptable learning — she is not in critical path until A3-Scale.

**Apple Intelligence does not bite.** A1 is a calibrated bet. Mitigation: improvements are defensible regardless of Apple response.

**AI products strip referers.** A2 will undercount. Mitigation: document methodology, compare future measurements to same methodology.

**Postgres autovacuum never ran on large tables.** Statistics are stale. Could cause planner issues. Mitigation: run ANALYZE on agents, entity_lookup, agent_jurisdiction_status at some point during sprint (low priority, not blocking).

## Rollback procedures

Each track has independent rollback:

**A1 rollback:** Revert commits. OG image generation behind feature flag. Schema.org changes in code.

**A2 rollback:** Schema columns can be dropped without affecting production. Dashboard panels are read-only.

**A3-Fix rollback per batch:** Fix scripts should record pre-state for rollback. If a fix introduces problems, revert specific rows.

**A3-Gate rollback:** promote_to_king() function is new code, not wired into existing crawlers. Can be removed without impact.

**A3-Scale rollback per batch:** UPDATE software_registry SET is_king = false WHERE entity_id IN (batch_list). Does not affect underlying entity data.

**Catastrophic rollback (Mac Studio failure during sprint):** Restore from 2026-04-10 backup. Provision Hetzner per ADR-003 Phase 0 as emergency acceleration. Lost work is the sprint deliverables themselves, not underlying data.

## What this sprint is NOT

To keep scope honest:

- Not hook-based CTR optimization. A2 establishes measurement, hook variants are a future sprint.
- Not browser extension, MCP distribution, Grok/X distribution, Google Dataset Search, Wikipedia integration. Those are separate future sprints.
- Not new verticals or language additions. Phase 2 and Phase 4 handle those.
- Not Cloudflare Workers scripts. No Worker-level optimization.
- Not Phase 0 cloud migration. That starts approximately 2026-04-15 separately.
- Not fixing Buzz. Ollama-Buzz decision deferred to Phase 0 window per 2026-04-10 discovery document.
- Not unconditionally scaling Kings to 500K. Scaling is gated on measurement per ADR-003 Addendum #4.

## References

- docs/adr/ADR-003-cloud-native-expansion-first.md
- docs/adr/ADR-003-addendum-baseline-discoveries.md
- docs/adr/ADR-003-addendum-2-claude-code-local.md
- docs/adr/ADR-003-addendum-3-sequence-revision.md
- docs/adr/ADR-003-addendum-4-leverage-sprint-pivot.md (authoritative for A3 structure)
- docs/strategy/phase-0-cloud-migration-plan.md
- docs/architecture/kings-definition.md (with corrections pending in M2)
- docs/status/2026-04-10-ollama-buzz-discovery.md
- docs/buzz-context.md
- docs/session-handoff-2026-04-10-morning.md (now superseded by this file and Addendum #4 for sprint structure)
- ~/nerq-baselines/2026-04-09-pre-migration/
- ~/nerq-backups/2026-04-10-pre-leverage-sprint/

---

*End of Leverage Sprint plan. Rewritten 2026-04-10 after Day 1 audit revealed Kings hypothesis unverified. Sprint is measurement-first, quality-first, scaling-last.*


---

## M5 Audit Status — DISPUTED (2026-04-10 afternoon)

An M5 audit was produced by Claude Code at docs/status/leverage-sprint-day-2-m5-audit.md (766 lines). During review, spot-check verification against the Postgres agentindex database revealed that **two of five key findings contained factual errors**:

1. **Finding 1** (5.8x Kings/non-Kings citation ratio) was claimed as a cross-registry score-controlled comparison. Verification showed the ratio comes from a single registry (npm). Only 1 registry (npm) has balanced Kings and non-Kings in the 80-100 trust score band. Two other registries in that band (pypi, vpn) have zero non-Kings.

2. **Finding 3** (ai_tool Kings underperform due to 100% selection) was based on a false premise. ai_tool is 34% Kings and 66% non-Kings, not "all seeded entities get is_king=true" as the audit claimed.

**Crawl bias finding (Finding 2) was CONFIRMED and is stronger than the audit stated.** auto_indexnow.py structurally protects Kings from LIMIT cutoff AND applies a 6-language multiplier loop to the Kings-dominated slug list. Kings are guaranteed 6x more IndexNow submissions than non-Kings, independent of any "AI preference."

**Do not proceed with M6 (A3-Fix), M7 (A3-Gate), or M8 (A3-Scale) based on the M5 audit summary as originally written.**

The full discrepancy analysis is in docs/status/leverage-sprint-day-2-m5-verification-notes.md. Next M5 session must start by reading that file.

**Revised M5 plan:**
- M5.1: Design controlled experiment (remove Kings prioritization from auto_indexnow.py for 7-14 days)
- M5.2: Collect unbiased citation data
- M5.3: Re-measure with corrected understanding (single-registry limitation acknowledged)
- M5.4: Draft ADR-005 decision framework (do not conclude until unbiased data exists)

**What we know definitively after 2026-04-10 verification:**
- Crawl bias is structural and confirmed (auto_indexnow.py:347-354)
- npm has 400 Kings + 3,110 non-Kings in 80-100 trust score band — only balanced registry
- 4 registries have 100% or near-100% Kings (vpn, country, charity, crypto) — not measurable
- 4 registries have 0 Kings — cannot test hypothesis at all
- The Kings hypothesis may still be directionally correct, but current evidence is insufficient

**Decision deferred:** Kings hypothesis validity. Target resolution: next M5 session with corrected methodology.