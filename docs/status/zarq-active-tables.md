# ZARQ Active Tables — Option A-light Migration Scope

**Date:** 2026-04-12
**Context:** Phase 0 Day 1 pre-flight — identifying active tables in `crypto_trust.db` for migration to PostgreSQL.
**Decision reference:** `docs/status/phase-0-day-0-decisions.md` — Decision 1 (ZARQ migration: Option A-light)

---

## Summary

- **Total tables in crypto_trust.db:** 67
- **Active (written within 7 days):** 8
- **Semi-active (written within 30 days):** 10
- **Inactive (>30 days):** 8
- **No timestamp column (UPSERT pattern or static):** 41
  - Of which **5 show recent code activity** (modified Python files within 7 days)

---

## Migration targets

### Tier A: Critical active production tables — migrate in Phase 0 Week 1

These are written daily and are directly in production serving paths. Must be on Postgres before cutover.

| Table | Last write | Rows | Role |
|---|---|---|---|
| nerq_risk_signals | 2026-04-12 02:34 | 6,355 | Tier 1 real-time risk scoring |
| crypto_ndd_alerts | 2026-04-12 04:32 | 1,530,189 | Crash detection alerts (large) |
| crypto_price_history | 2026-04-12 | 1,125,586 | Historical prices for analysis |
| external_trust_signals | 2026-04-12 09:18 | 22,498 | Trust score dimension source |
| compatibility_matrix | 2026-04-12 07:00 | 18,741 | Package compatibility data |
| chain_dex_volumes | 2026-04-12 03:00 | 316 | DEX volumes per chain |
| crypto_pipeline_runs | 2026-04-12 02:00 | 371 | Pipeline operational metadata |
| agent_dashboard | 2026-04-11 09:00 | 15,986 | Daily dashboard aggregates |

### Tier A-extended: UPSERT tables with active code references

No ts column but Python code modifying them has been edited within 7 days. Likely written via UPSERT pattern without timestamp updates.

| Table | Rows | Code refs / recent | Role |
|---|---|---|---|
| crypto_ndd_daily | 230,412 | 35 / 3 recent | Daily crash detection summary |
| crypto_rating_daily | 3,743 | 33 / 2 recent | ZARQ rating display source |
| vitality_scores | 15,144 | 13 / 2 recent | Trust score dimension |
| defi_yields | 18,784 | 10 / 1 recent | DeFi yield data (Tier 2) |

### Tier B: Semi-active — migrate if schedule permits

Written within 30 days but not daily. Low risk to defer to post-Phase 0 if needed.

| Table | Last write | Rows | Role |
|---|---|---|---|
| nerq_risk_alerts | 2026-04-01 02:34 | 25 | Risk alert log |
| agent_dependencies | 2026-03-22 05:35 | 13,262 | Package deps metadata |
| published_cve_alerts | 2026-03-21 07:30 | 40 | Compliance CVE alerts |
| ecosystem_index | 2026-03-20 | 42 | Ecosystem categorization |
| agent_cost_estimates | 2026-03-18 04:00 | 17,773 | Pricing estimates |
| agent_pricing | 2026-03-18 03:00 | 1,116 | Agent pricing |
| agent_rate_limits | 2026-03-18 03:30 | 51 | Rate limit specs |
| agent_frameworks | 2026-03-15 09:35 | 4,787 | Framework detection |
| chain_developer_activity | 2026-03-14 02:00 | 40 | Chain dev stats |
| framework_stats | 2026-03-13 11:40 | 17 | Framework stats |

### Tier C: Deferred — post-Phase 0 cleanup project

47 tables fall into this category:
- 8 inactive tables (last write >30 days ago)
- Most no-ts tables (static reference data or dead code)

These will be handled in a separate cleanup project after Phase 0 stable. Inactive historical tables may be archived or dropped.

**Key examples in Tier C:**
- `crash_model_v3_predictions` (31,781 rows, last write 2026-02-23)
- `defi_tvl_history` (113,633 rows, last write 2026-02-28)
- `defi_stablecoin_flows` (17,969 rows, last write 2026-02-28)
- `defi_yield_history` (455,229 rows, last write 2026-03-05)
- `crypto_regime_backtest*` and `crypto_portable_alpha*` (backtest results, low access)

---

## Migration scope summary

- **Tier A + A-extended (MUST migrate):** 12 tables, ~3M rows, ~150-300 MB
- **Tier B (SHOULD migrate if time):** 10 tables, ~37K rows, ~5-10 MB
- **Tier C (DEFER):** 47 tables, out of Phase 0 scope

**Total migration volume for Phase 0:** 12-22 tables, ~3 million rows, ~155-310 MB. Well within Option A-light budget of 4-6 hours.

---

## Migration execution order (Phase 0 Day 2-3)

1. **Day 2:** Create Postgres schema matching SQLite for all Tier A + A-extended tables. Test schema on a fresh Postgres instance before migrating data.
2. **Day 2:** Bulk-copy Tier A data via `sqlite3 .dump` → transform → `psql \copy`. Verify row counts match.
3. **Day 3:** Update `agentindex/crypto/*.py` modules to write Postgres instead of SQLite for Tier A tables.
4. **Day 3:** Dual-write period — both SQLite and Postgres accept writes for 24 hours. Verify parity.
5. **Day 4:** Cut over reads to Postgres. Deprecate SQLite write path for Tier A tables.
6. **Day 4-5:** Tier B migration (same pattern).
7. **Post-Phase 0:** Cleanup project addresses Tier C.

---

*End of ZARQ Active Tables analysis.*
