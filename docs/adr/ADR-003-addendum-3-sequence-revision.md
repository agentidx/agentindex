# ADR-003 Addendum #3: Sequence Revision — Leverage Sprint Before Phase 0

**Parent:** ADR-003 Cloud-Native Expansion-First Architecture with Freshness SLA
**Related:** ADR-003 Addendum (baseline discoveries), ADR-003 Addendum #2 (Claude Code local execution)
**Date:** 2026-04-09 (late evening)
**Author:** Anders + Claude session
**Status:** Accepted as addendum to ADR-003

## Context

The original ADR-003 implementation plan (`docs/strategy/phase-0-cloud-migration-plan.md`) established this sequence:

1. Phase 0: Cloud migration (2 weeks)
2. Phase 1: Parameterize Norwegian language model (3-5 days)
3. Phase 2: 50-language sprint (5-10 days)
4. Phase 3: Vertical pipeline (3-5 days)
5. Phase 4: 100-vertical sprint (2-3 weeks)

Leverage Sprint (`docs/strategy/leverage-sprint-plan.md`), added later on 2026-04-09, was initially positioned to run after Phase 0 and in parallel with Phase 1.

On the evening of 2026-04-09, Anders challenged the sequencing on momentum grounds. The discussion that followed concluded that Leverage Sprint should run **before** Phase 0, not after.

## Decision

**Leverage Sprint starts 2026-04-10. Phase 0 cloud migration is deferred until Leverage Sprint is at least in its background-execution phase (5-7 days from 2026-04-10).**

Revised sequence:

1. **Leverage Sprint** (5-6 days active, then background batches) — starts 2026-04-10
2. **Phase 0: Cloud migration** (2 weeks) — starts approximately 2026-04-15 while Leverage Sprint background batches continue
3. Phase 1: Parameterize Norwegian model
4. Phase 2: 50-language sprint
5. Phase 3: Vertical pipeline
6. Phase 4: 100-vertical sprint

Leverage Sprint's A3 Kings batches may still be running in the background on Mac Mini during Phase 0 Week 1. They pause during Phase 0 cutover (~24 hours) and resume after.

## Rationale

Five arguments drove the sequence reversal:

1. **Mac Mini is idle capacity that costs nothing to use today.** It was connected to Mac Studio the same day this decision was made. Waiting two weeks to deploy it for productive work wastes 14 days of compute that is already paid for.

2. **Acute Mac Studio risks are mitigated.** The autoheal restart loop was fixed on 2026-04-09 morning. Sudo-blocked fixes are accepted risks. The remaining risk is hardware failure (fire, flood, theft, drive death) with an estimated probability of 2-5% per week. Paying two weeks of momentum to reduce a 2-5% weekly risk is a poor trade.

3. **Momentum is not a soft factor.** The expansion plan's trajectory (10-15% day-over-day growth during active development) came from running hard, not from pausing for infrastructure work. Two weeks of pause can cost more in delayed trigger-timing than Phase 0 saves in reduced risk.

4. **Leverage Sprint reduces migration risk when Phase 0 arrives.** Running Kings scaling and AI-to-human tracking first means Phase 0 migrates a better-instrumented and more optimized site. A2 tracking establishes a baseline we can verify against after cutover. A3 proves our ability to run batch operations on 500K+ entities — exactly the muscle needed for Phase 0's Postgres transfer.

5. **For a solo bootstrapper with a long time horizon, momentum first is the correct operating model.** The alternative (robustness first) is appropriate for VC-funded startups optimizing for survival until the next funding round. Nerq optimizes for every day of growth, which aligns with momentum-first.

## Risks accepted

- **Mac Studio hardware failure during Leverage Sprint window** (2-5% probability per week). If this happens, Leverage Sprint work-in-progress (Kings batches, dashboards) is lost. Recovery: restore from backups taken before sprint start, then provision Hetzner as emergency measure per ADR-003. No data loss on original entities; only lost work is the sprint's own deliverables.

- **Parallel complications between Leverage Sprint and Phase 0.** A3 Kings enrichment writes to Postgres continuously. Phase 0 Postgres transfer needs a consistent snapshot. Mitigation: pause A3 writes during pg_dump (~30 minutes) and during cutover (~24 hours). Resume after each.

- **Mac Mini under tension for the first time.** Mac Mini was connected same-day and has not run production workloads yet. First batch may reveal throughput limits or connection issues. Mitigation: start small (1000 entities) on Mac Mini, scale up only after stability confirmed.

## Safety requirement before starting

Before Leverage Sprint begins, a full backup of the current production state must be taken. Specifically:

1. **Postgres full dump** via pg_dump to a local file on Mac Studio
2. **SQLite copies** of analytics.db, crypto_trust.db (both locations)
3. **Sacred fixtures refresh** — re-capture the 10 HTML snapshots from baseline to ensure they are current
4. **Git working tree clean and pushed** so code state is recoverable
5. **List of LaunchAgents** confirmed (already done in baseline)

This backup is the fallback if Mac Studio fails during Leverage Sprint. Without it, recovery is much harder.

## Coordination protocol with Phase 0

When Phase 0 starts (~2026-04-15), Leverage Sprint's A3 Kings batches continue running in the background on Mac Mini. The coordination rules are:

- **A3 pauses during pg_dump** (estimated 30 minutes)
- **A3 pauses during Postgres transfer** (estimated 8-14 hours)
- **A3 pauses during Phase 0 cutover** (estimated 24 hours)
- **A3 resumes on Hetzner primary after cutover** with the same entity queue, skipping entities already processed

The pause-and-resume is managed via a simple work-log file that both machines read and write. If A3 is mid-batch when a pause signal arrives, the current batch completes, then pauses. No batches are left in half-processed state.

## What does not change

- ADR-003 core architecture ✓
- Phase 0-4 sequence ordering within itself ✓ (just delayed by ~1 week)
- Freshness SLA targets ✓
- Budget cap at $100/month ✓
- Mac Studio + Mac Mini as optional accelerators (now more valuable than originally planned) ✓
- Expansion-first philosophy ✓ — this decision strengthens rather than weakens it

## Final timeline (revised from ADR-003)

| Period | Focus | Start |
|---|---|---|
| Week 1 (Apr 10-15) | Leverage Sprint active phase | **2026-04-10** |
| Weeks 2-3 (Apr 15-29) | Phase 0 cloud migration + A3 background | 2026-04-15 |
| Weeks 4 (Apr 29 - May 4) | Phase 1 parameterize Norwegian | ~2026-04-29 |
| Weeks 5-6 (May 4-18) | Phase 2 50-language sprint + Phase 3 vertical pipeline | ~2026-05-04 |
| Weeks 7-9 (May 18 - Jun 8) | Phase 4 100-vertical sprint | ~2026-05-18 |

Total: 9 weeks from today to "100 verticals × 50 languages live with freshness SLA", approximately 1 week slower than the most aggressive Phase 0-first scenario but with momentum preserved and Mac Mini fully utilized.

## References

- `docs/strategy/leverage-sprint-plan.md` (rewritten 2026-04-09 evening to reflect this sequence)
- `docs/strategy/phase-0-cloud-migration-plan.md` (unchanged — still canonical for Phase 0-4 execution, just starts later)
- `docs/session-handoff-2026-04-10-morning.md` (start-here document for next session)

---

*End of ADR-003 Addendum #3.*
