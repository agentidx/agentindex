# Phase 0 Day 0 — Pre-flight Decisions

**Date:** 2026-04-12
**Authors:** Anders + Claude (chat session)
**Status:** Approved, ready for Phase 0 Day 1
**Related:** `docs/strategy/phase-0-cloud-migration-plan.md`, `docs/adr/ADR-003-addendum-baseline-discoveries.md`

---

## Context

Phase 0 cloud migration (Nerq + ZARQ from Mac Studio to Hetzner Nbg + Hel + CPX21 worker) was scheduled to start ~2026-04-15 per ADR-003 Addendum #3. The baseline capture on 2026-04-09 flagged several open decisions that had to be made before Day 1 execution.

This document records the 3 decisions taken on 2026-04-12 (Day 0 preflight). All 3 are now locked — Phase 0 Day 1 execution proceeds on these assumptions.

---

## Decision 1 — ZARQ migration strategy: Option A-light

**Context:** ZARQ runs on SQLite (`crypto_trust.db`, 1.2 GB, 69 tables) not Postgres. Postgres replication (Mac Studio → Nbg → Hel) does not cover ZARQ data. Without action, ZARQ would remain on Mac Studio as a single-point-of-failure.

**Data inspection (2026-04-12):**
- crypto_trust.db: 1.2 GB, 69 tables total
- Active tables (last-write within past week): ~10-15, including `nerq_risk_signals` (updated 2026-04-12 02:34), `defi_protocol_tokens`, `crypto_rating_daily`, `nerq_risk_alerts`, `crypto_pipeline_runs`
- Inactive tables (last-write >3 months ago): ~50+, mostly historical experiments and snapshots

**Options considered:**
- **A:** Full migration — move all 69 tables to Postgres. +1-2 days Phase 0 time.
- **B:** Litestream replication — SQLite WAL streamed to Hetzner. Fast setup but leaves ZARQ brittle, same lock contention risks as analytics.db.
- **C:** Dual-deploy — Nerq migrates, ZARQ stays on Mac Studio. Extends "Mac Studio critical" window.
- **A-light:** Migrate only the ~10-15 active tables to Postgres. Leave inactive historical tables in SQLite for separate cleanup post-Phase 0.

**Decision: A-light.**

**Rationale:**
- Active ZARQ data is small (~100 MB estimated, not 1.2 GB). Migration is feasible in 4-6 hours, not 1-2 days.
- ZARQ becomes first-class HA citizen: Postgres replication covers it automatically after migration.
- Avoids SQLite-WAL-locking failure modes that caused analytics-dashboard incidents (see commit 1f88ca4).
- Inactive tables can be cleaned up later without blocking Phase 0.
- Refactor surface is bounded (only active tables, not all 69).

**Implementation plan (Phase 0 Day 1-3):**
1. Identify exact active table list via `SELECT name, MAX(rowid_or_timestamp) FROM ...` across all 69 tables
2. Generate Postgres DDL from SQLite schema for active tables
3. Bulk-copy active data via pg_loader or direct COPY
4. Update `crypto_pipeline.py` and active ZARQ modules to write Postgres
5. Dual-write for 24-48h to verify parity
6. Cut over ZARQ reads to Postgres
7. Deprecate SQLite write path for active tables (keep file for inactive tables until cleanup project)

**Out of scope:** Migration of inactive historical tables. Scheduled as separate post-Phase 0 cleanup project.

---

## Decision 2 — agent_jurisdiction_status table transfer: Option A (as-is)

**Context:** `agent_jurisdiction_status` is 57 GB (64% of the 90 GB Postgres database). Baseline estimated Tailscale transfer time as 8-14 hours. Schema is 260M rows from 5M agents × 52 jurisdictions — classic wide-row anti-pattern that could be refactored to <10 GB with a pivot.

**Options considered:**
- **A:** Transfer as-is. 8-14h overnight, no refactor.
- **B:** Trim before transfer. Remove inactive jurisdictions or historical snapshots. Cut table ~50%.
- **C:** Refactor schema first. Pivot to compact format, <10 GB. 2-4 days work.

**Decision: A.**

**Rationale:**
- All 52 jurisdictions remain relevant for compliance scoring. No safe basis for trim.
- Refactor (Option C) is 2-4 days of careful data modeling + query migration + testing. Does not belong in Phase 0.
- 8-14h transfer is acceptable when run overnight during low-traffic window.
- Streaming replication picks up after initial transfer — no ongoing concerns.
- Schema refactor becomes separate post-Phase 0 optimization project.

**Implementation plan (Phase 0 Day 3-4):**
1. Start pg_dump on Mac Studio, compress to file
2. rsync to Hetzner Nbg (rsync --partial for resume capability if Tailscale hiccups)
3. pg_restore on Nbg
4. Verify row counts match
5. Start streaming replication
6. Overnight completion expected, monitor in morning

**Out of scope:** Schema refactor to compact format. Tracked as separate follow-up task after Phase 0 stable.

---

## Decision 3 — Ollama / auto_publisher.py: Keep on Mac Studio as accelerator

**Context:** `~/agentindex/agentindex/crypto/auto_publisher.py` uses Ollama qwen2.5:7b for ZARQ article generation. Ollama runs as LaunchAgent `homebrew.mxcl.ollama`. After Phase 0, Hetzner CPX41 (16GB RAM, no GPU) cannot run qwen2.5:7b efficiently. Mac Studio M1 Ultra (48-core GPU) is purpose-built for it.

**Options considered:**
- **Migrate:** Move auto_publisher to Hetzner, swap Ollama for API calls to Claude/OpenAI. Breaks the "zero-API-cost" principle and creates recurring API spend.
- **Drop:** Disable auto_publisher. ZARQ loses automated article pipeline.
- **Keep on Mac Studio as accelerator:** auto_publisher continues on Mac Studio, production ZARQ on Hetzner calls Mac Studio Ollama via Tailscale when article generation is triggered.

**Decision: Keep on Mac Studio as accelerator.**

**Rationale:**
- Mac Studio becomes optional accelerator after Phase 0 — this is perfect use of that capacity.
- Hetzner CPX41 cannot run 7B models at reasonable speed without GPU.
- API alternative violates $100/month cost cap and creates vendor lock-in.
- If Mac Studio dies, auto_publisher pauses — acceptable degradation (ZARQ article generation is content enhancement, not core product functionality).
- Aligns with Buzz 2.0 spec's recommended hosting topology (Mac Studio as LLM accelerator for Buzz secondary instance).

**Implementation plan (Phase 0 Week 2):**
1. When ZARQ moves to Hetzner, change auto_publisher Ollama URL from `localhost:11434` to `mac-studio-tailscale-ip:11434`
2. Verify Tailscale latency acceptable (<500ms round-trip)
3. Add health check: if Mac Studio unreachable, auto_publisher queues articles for retry (doesn't fail hard)
4. Log auto_publisher invocations so we can see if it's working post-migration

**Out of scope:** Upgrading Buzz's LLM infrastructure. Tracked separately in Buzz 2.0 spec (see `docs/strategy/buzz-2.0-spec.md`).

---

## Summary

| Decision | Choice | Impact on Phase 0 |
|---|---|---|
| ZARQ migration | A-light (active tables only) | +4-6h in Phase 0 Day 1-3 |
| agent_jurisdiction_status | A (transfer as-is) | 8-14h overnight during Day 3-4 |
| Ollama / auto_publisher | Keep on Mac Studio | No Phase 0 work, config swap in Week 2 |

**Phase 0 Day 1 can proceed as planned.** No further pre-flight decisions outstanding.

---

## Related follow-up projects (post-Phase 0)

1. **Inactive ZARQ tables cleanup** — drop or archive the ~50+ SQLite tables in `crypto_trust.db` that haven't been written in >3 months.
2. **agent_jurisdiction_status schema refactor** — pivot 260M-row wide structure to compact format, expected <10 GB from 57 GB.
3. **Buzz LLM upgrade** — separate from this decision. Tracked in `docs/strategy/buzz-2.0-spec.md`.

---

*End of Phase 0 Day 0 Decisions.*
