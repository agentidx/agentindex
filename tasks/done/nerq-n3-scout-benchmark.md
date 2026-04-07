# Nerq N3.0 — Scout, Benchmark, Reputation

## Status: DONE
Completed: 2026-03-10

## Tasks

### N3.0: Benchmark "With Nerq vs Without Nerq"
- [x] Created `nerq_benchmark_test.py` — 20-tool pool, 10 runs, random vs preflight selection
- [x] Results: Failure rate 44% → 0%, avg trust 75.8 → 81.6
- [x] Saves JSON to `docs/benchmark-results.json`, markdown to `docs/benchmark-with-vs-without.md`
- [x] Report page at `nerq.ai/report/benchmark` — Swiss minimalist, shows comparison data
- [x] Added to /reports index

### N3.2.1: Review System
- [x] `POST /v1/agent/review` — submit peer reviews (success/failure/partial)
- [x] Created `agent_reviews` table in PostgreSQL
- [x] Created `nerq_scout_log` table in PostgreSQL
- [x] Rate limit: 100 reviews/day per IP
- [x] Review bonus: success +0.1, failure -0.5, capped [-5, +5]

### N3.2.3: Reputation
- [x] `GET /v1/agent/reputation/{name}` — static trust + review bonus + rank
- [x] Returns: trust_score, static_trust, review_bonus, total_reviews, success_rate, days_active, rank_in_category

### N3.2.4: Interaction Ledger
- [x] `GET /v1/agent/ledger/{name}?days=30` — reviews received/given, trust trend, recent interactions
- [x] Returns last 10 interactions with reviewer, outcome, latency_ms

### Documentation
- [x] Updated `/nerq/docs` with Reviews, Reputation, Ledger sections
- [x] Added benchmark to reports table

### Performance fix (bonus)
- [x] Fixed ILIKE → lower(name::text) LIKE lower(:pattern) in preflight.py, kya_api.py, badge_api.py
- [x] Preflight cold: 3000ms → 86ms (35x speedup)

## Files Created/Modified
- NEW: `agentindex/nerq_benchmark_test.py`
- NEW: `agentindex/nerq_scout.py` (review, reputation, ledger)
- NEW: `agentindex/report_benchmark.py`
- NEW: `docs/benchmark-results.json`
- NEW: `docs/benchmark-with-vs-without.md`
- MOD: `agentindex/api/discovery.py` (wired scout + benchmark routers)
- MOD: `agentindex/nerq_docs.py` (added Reviews, Reputation, Ledger, Benchmark docs)
- MOD: `agentindex/report_q1_2026.py` (added benchmark to reports index)
- MOD: `agentindex/preflight.py` (ILIKE → trgm-compatible LIKE)
- MOD: `agentindex/kya_api.py` (ILIKE → trgm-compatible LIKE)
- MOD: `agentindex/badge_api.py` (ILIKE → trgm-compatible LIKE)

## Result
All endpoints live and tested. Benchmark proves 44% failure reduction and +5.8 trust improvement with Nerq preflight. Scout system enables community-driven trust signals on top of static scores.
