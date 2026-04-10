# ADR-003 Addendum #4: Leverage Sprint Pivot — Measurement-First, Kings Hypothesis Unverified

**Parent:** ADR-003 Cloud-Native Expansion-First Architecture with Freshness SLA
**Related:** ADR-003 Addendum #3 (Sequence Revision, 2026-04-09), kings-definition.md (2026-04-10)
**Date:** 2026-04-10 (morning, Leverage Sprint Day 1)
**Author:** Anders + Claude session
**Status:** Accepted as addendum to ADR-003

## Context

Leverage Sprint Day 1 began with a read-only audit of the Kings system executed by Claude Code on Mac Studio. The audit was commissioned as a straightforward "document what exists" task. It returned findings that changed our understanding of the Nerq Kings architecture materially, and forced a re-evaluation of the sprint's central hypothesis.

Three things were discovered during the audit and its follow-up verification:

1. There is no centralized King classification function. Each of the 20+ registries sets is_king independently at crawl time, with rules scattered across individual seed scripts and crawlers. There is no promote_to_king(entity) function to call.

2. Of the 37,688 current Kings, 30,442 (81%) are at king_version = 0 and have never been enriched beyond their initial seed. 99.3% lack populated dimensions data. 225 have broken or missing descriptions. All 158 country Kings have identical trust score 48.2 (likely a scoring bug). The king_refresh.sh script that runs weekly only bumps enriched_at timestamps without validating any content.

3. The hypothesis that Kings receive more AI citations than non-Kings has never been measured in Nerq's codebase. The flywheel dashboard counts Kings by quantity (total, enriched by timestamp, indexable). It does not measure Kings yield versus non-Kings yield. The dashboard's own text acknowledges this: "Yield measurement available after 3-5 days of AI re-crawling." citation_tracker.py (192 lines) contains zero references to is_king. No file in the codebase joins the Kings flag to the requests table to compare bot crawl rates or AI-attributed human traffic.

The hypothesis that motivated A3 Kings Scaling in the original leverage-sprint-plan.md was therefore never evidence-based. It was a reasonable inference ("more structured data should produce more AI citations") that was recorded in strategic documents as if it had been measured.

## The decision

**A3 Kings Scaling target of 500K is retained as the ambition, but gated on measurement. A3 is restructured into four phases with explicit gating between them. No scaling occurs until the hypothesis is measured and confirmed.**

### Phase A3-Measure (new, highest priority)

Build the measurement infrastructure to test the Kings hypothesis before scaling anything. Concretely: extend flywheel_dashboard.py or citation_tracker.py to produce a Kings vs non-Kings split of AI bot crawl rates, per-source citation rates (ClaudeBot, GPTBot, PerplexityBot, Applebot, others), and AI-attributed human traffic once A2 tracking is live. This uses A2 tracking infrastructure where possible to avoid duplicate work.

Target output: a panel or query result that says "over the last N days, Kings received X AI bot visits per page per day; non-Kings received Y AI bot visits per page per day." If X > Y by a material margin, the hypothesis is validated. If X is roughly equal to Y or lower, the hypothesis is disproven and A3-Scale is cancelled.

### Phase A3-Fix

Repair the 37,688 existing Kings to meet a defined quality bar before attempting any new promotions. Success criteria:

1. Zero Kings with NULL, empty, or sub-10-character descriptions (currently 225)
2. Zero Kings with trust_score below 30, either by fixing the score or by demoting the entity (currently 28)
3. Country Kings scoring bug investigated and either fixed or documented as known limitation (currently all 158 countries have identical 48.2)
4. Dimensions column populated for as many Kings as possible given available data; accept that this may be much lower than 100% if the underlying data does not exist for all registries
5. A reproducible validator script at scripts/validate_kings.py that can be run against the full Kings set and report failures by category

A3-Fix runs on Mac Studio writing to primary Postgres. Mac Mini reads from replica and runs the validator in parallel against production URLs to check HTML-level correctness (not just database state).

### Phase A3-Gate

Build a central promote_to_king(entity_id, reason) function with explicit, auditable rules. This function replaces the scattered per-crawler logic for future promotions. It does not retroactively change existing Kings. The function takes an entity ID, validates that the entity meets the central Kings criteria (derived from A3-Fix's validator), and either promotes or rejects with a logged reason.

A3-Gate output: a single function, documented rules, unit tests, and an ADR describing the gating rules as the authoritative source. Old crawlers continue to work but are scheduled for migration to the central function in a future sprint.

### Phase A3-Scale — gated on measurement

A3-Scale runs if and only if A3-Measure shows that the Kings hypothesis is validated by at least 5-7 days of post-A3-Fix measurement data. If the measurement window shows Kings receive materially more AI bot crawls or higher AI-attributed human traffic than comparable non-Kings, A3-Scale promotes additional entities via the A3-Gate function toward the 500K target originally envisioned in leverage-sprint-plan.md.

The 500K target is retained as the ambition. Anders is committed to that scale if the hypothesis holds. What changes is that scaling does not begin until measurement confirms the hypothesis, and the rate of promotion may be adjusted based on what the measurement data reveals about where Kings effects are strongest (e.g., certain registries or verticals may show larger effects than others, which would shape which entities get promoted first).

If the measurement window shows no material difference, or if Kings underperform non-Kings, A3-Scale is paused while the team investigates whether the hypothesis needs refinement, whether the measurement methodology was flawed, or whether Kings as a concept should be reconsidered. Cancellation is a possible outcome but not the default — the default is re-examination before abandonment.

## Revised sprint ordering

The original ordering in leverage-sprint-plan.md ran A1, A2, and A3 in parallel from Day 1 with A3 dominating the effort allocation. The revised ordering is:

1. Day 1 (today, 2026-04-10) — audit and documentation only. No production writes. Strategic decisions recorded in this addendum.

2. Day 2 — A2 AI-to-human tracking schema deployed first. This builds measurement infrastructure that A3-Measure will extend. A1 Apple audit happens in parallel on Mac Studio as a smaller track.

3. Day 3 — A3-Measure built as an extension of A2. Kings vs non-Kings split added to dashboard or new query exposed. Measurement begins collecting baseline immediately. A1 Apple deploy begins.

4. Days 3-5 — A3-Fix executes in parallel with A3-Measure collecting data. Mac Studio writes fixes to primary Postgres. Mac Mini runs HTML-level validator reading from replica and fetching production URLs.

5. Days 5-6 — A3-Gate function built, tested, committed. A1 Apple deploy completes.

6. Days 7+ — A3-Measure data reviewed. Decision: proceed to A3-Scale or cancel. If proceed, A3-Scale runs into the background weeks alongside Phase 0 cloud migration.

Phase 0 cloud migration start date remains approximately 2026-04-15 per ADR-003 Addendum #3. Leverage Sprint active phase now ends on Day 5-6 instead of Day 5-6 with A3 still running — the difference is that A3-Scale is no longer assumed to happen, and the sprint's success criteria are measurement-oriented rather than volume-oriented.

## Compute allocation (Mac Studio and Mac Mini)

Mac Studio handles:
- All A1 deliverables (production code deployment)
- All A2 deliverables (schema migration on analytics.db which lives only on Mac Studio)
- A3-Measure query development and deployment
- A3-Fix writes to primary Postgres
- A3-Gate function development and testing
- Production serving (unchanged)

Mac Mini handles:
- TTFB measurements for A1 against 10K entity URLs from a second geographic perspective
- Kings HTML-level validator running against production URLs in parallel with Mac Studio writes
- Backfill queries for A2 reading from analytics.db replica (to be set up if not already)
- Read-only queries for A3-Measure sampling and validation
- Background crawl of competitors as low-priority filler

Mac Mini does NOT:
- Write to primary Postgres
- Promote new Kings
- Run the A3-Gate function
- Deploy code changes

This is a write/read split appropriate for a replica relationship. It is a narrower role than the original sprint plan envisioned (which assumed Mac Mini could autonomously run a full enrichment pipeline), but it is architecturally correct given what the audit revealed.

## What does not change

- ADR-003 core architecture
- ADR-003 Addendum #3 sequence (Leverage Sprint before Phase 0)
- Phase 0 cloud migration plan timing (approximately 2026-04-15)
- Freshness SLA targets
- Budget cap at 100 USD per month
- Expansion-first philosophy
- Welcome-all-traffic policy

## What does change

- A3 Kings Scaling target of 500K is retained as the ambition but gated on measurement. A3 is now a measurement, quality, and systematic-scaling track in sequence. Scaling begins after measurement confirms the hypothesis and existing Kings are fixed.
- Sprint success criteria pivot from "Kings deployed in bulk without verification" to "hypothesis measured, existing Kings repaired, scaling gate built, scaling begun if measurement justifies it."
- A2 moves to highest-priority deployment target on Day 2 because it provides measurement infrastructure that A3 depends on.
- Mac Mini role reduced from "autonomous enrichment pipeline" to "read-heavy validation and measurement support."

## Explicit acceptance of measurement authority

If A3-Measure shows that Kings do not outperform non-Kings after the 5-7 day window, we will not execute A3-Scale on autopilot. The sprint will instead:

- Document the finding in a post-sprint retrospective
- Publish a follow-up ADR addendum recording the measurement result
- Review whether the hypothesis needs refinement, the methodology was flawed, or Kings as a concept should be rethought
- Redirect scaling resources to A1 Apple deeper work, A2 hook optimization experiments, or other tracks until the Kings question is resolved

This is not a failure mode. It is the point of measurement. The cost of running A3-Measure and A3-Fix is recoverable regardless of the hypothesis outcome because the fixes improve existing content quality independent of any citation effect. Anders retains the 500K target as the ambition; the gate exists to ensure the scaling effort is deployed toward an outcome backed by evidence.

## Responsible party for the measurement decision

Anders is the decision maker on whether A3-Scale executes after the measurement window. Claude (chat session, not Claude Code) will present the measurement data with an explicit recommendation but will not execute A3-Scale without Anders' explicit go-ahead. Claude Code on Mac Studio is not authorized to make this decision autonomously.

## References

- docs/architecture/kings-definition.md — the audit that revealed the findings
- docs/strategy/leverage-sprint-plan.md — sprint plan to be rewritten with this addendum as the authoritative source
- agentindex/flywheel_dashboard.py lines 350-365 and 955-991 — current Kings dashboard queries, do not measure citation correlation
- agentindex/intelligence/citation_tracker.py (192 lines) — citation tracking code, contains zero Kings references
- Previous session strategic documents that recorded the Kings to citations hypothesis as if measured — not cited individually here, but flagged as a source of the confusion we are now correcting

---

*End of ADR-003 Addendum #4.*
