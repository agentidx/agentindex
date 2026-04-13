# Buzz Protocol Update: ZARQ Dual-Write ACTIVE

**Activated:** 2026-04-13 ~07:55 CEST
**Commits:** ce35c53 → d87b45d → e3d5967 → 9c9da90
**Status:** LIVE in production

## What changed

Every write to ZARQ Tier A SQLite tables now mirrors to PostgreSQL `zarq.*`
schema via `agentindex/crypto/dual_write.py`.

**Tier A tables (12):**
crypto_ndd_alerts, crypto_price_history, crypto_ndd_daily, external_trust_signals,
defi_yields, compatibility_matrix, agent_dashboard, vitality_scores,
nerq_risk_signals, crypto_rating_daily, crypto_pipeline_runs, chain_dex_volumes

## Guarantees

- **SQLite remains source of truth.** Never blocked by Postgres errors.
- Postgres write failures logged to `~/agentindex/logs/dual_write_errors.log`
- Feature flag: `ZARQ_DUAL_WRITE=1` set in 10 LaunchAgents
- Connection pool: `ThreadedConnectionPool(minconn=2, maxconn=10)` via `/tmp` unix socket

## Active LaunchAgents with flag

com.nerq.crypto-daily, com.nerq.community-signals, com.nerq.compat-matrix,
com.nerq.dashboard-data, com.nerq.dex-volumes, com.nerq.openssf-crawler,
com.nerq.osv-crawler, com.zarq.vitality-recalc, com.zarq.vitality-report,
com.zarq.mcp-sse

## What Buzz should know / do

1. **DO NOT** set ZARQ_DUAL_WRITE=0 or remove it without explicit instruction from Anders
2. **DO** monitor `~/agentindex/logs/dual_write_errors.log` — grow rate should be near zero
3. **DO** watch Postgres replication lag via `pg_stat_replication` on Mac Studio
   - Nbg (100.119.193.70): expect streaming, 0 lag
   - Hel (100.79.171.54): currently catchup after basebackup — will reach streaming
4. If you encounter a Postgres outage: SQLite writes continue normally.
   Just alert Anders, don't try to "fix" by disabling dual-write.
5. **Gap backfill PENDING** — ~8K rows written to SQLite between migration
   (12 Apr evening) and dual-write activation (13 Apr ~07:55). One-time COPY
   needed before reads can switch to Postgres.

## Next milestones

- **+2h** verify deltas stop growing (dual-write catches all new writes)
- **+24h** run backfill of 8K gap rows
- **+48h** if dual_write_errors.log still empty → consider switching ZARQ read path to Postgres
- **Phase 0 Day 4+**: ZARQ Tier B migration, app deployment Nbg+Hel, cutover

## Rollback if needed

```bash
# Disable dual-write (SQLite continues normally):
for plist in ~/Library/LaunchAgents/com.nerq.crypto-daily.plist \
             ~/Library/LaunchAgents/com.nerq.community-signals.plist \
             ~/Library/LaunchAgents/com.nerq.compat-matrix.plist \
             ~/Library/LaunchAgents/com.nerq.dashboard-data.plist \
             ~/Library/LaunchAgents/com.nerq.dex-volumes.plist \
             ~/Library/LaunchAgents/com.nerq.openssf-crawler.plist \
             ~/Library/LaunchAgents/com.nerq.osv-crawler.plist \
             ~/Library/LaunchAgents/com.zarq.vitality-recalc.plist \
             ~/Library/LaunchAgents/com.zarq.vitality-report.plist \
             ~/Library/LaunchAgents/com.zarq.mcp-sse.plist; do
  sed -i '' 's|<string>1</string>|<string>0</string>|' "$plist"
  launchctl unload "$plist"; launchctl load "$plist"
done
```

Backup of original plists: `~/Library/LaunchAgents/.bak-20260413-0755/`
