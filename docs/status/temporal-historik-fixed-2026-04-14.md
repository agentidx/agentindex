# Temporal History Infrastructure — Fixed 2026-04-14

## What was done

### DEL 1: Fixed daily_snapshots LaunchAgent

**Root causes (two bugs):**
1. `com.nerq.signal-warehouse` plist had no `DATABASE_URL` — SQLAlchemy defaulted to `localhost` which connected to the read-only Mac Studio replica instead of the Nbg primary
2. No `statement_timeout` set — inherited the API's 5s timeout, causing INSERT queries on large registries (npm: 528K rows, nuget: 641K rows) and the trust_changes JOIN to fail

**Fixes applied:**
- Added `DATABASE_URL=postgresql://anstudio@100.119.193.70/agentindex` to plist
- Added session-level `SET statement_timeout = '300s'` at start of main()
- Batched agent snapshots (10K per batch instead of 100K single INSERT)
- Made each collector resilient — failures in one don't crash the whole pipeline
- Fixed `ON CONFLICT` clauses to use the new unique index `idx_ds_unique`
- Added unique index `idx_ds_unique ON daily_snapshots (date, entity_type, entity_id, registry)`
- Removed 482,811 duplicate rows from previous runs

**Verified run results (2026-04-14):**
| Collection | Rows | Status |
|-----------|------|--------|
| Software registry | 2,466,757 | All 30 registries |
| Agent snapshots | 96,644 | Top 100K by stars (batched) |
| Website snapshots | 30,000 | All website_cache |
| Entity ratings | 102 | All rated entities |
| Trust changes | 372 | First time working! |
| Major signal events | 193 | >10 point changes |
| AI behavior | 4,999 | Bot access patterns |
| Ecosystem metrics | 30 | Per-registry aggregates |
| **Total runtime** | | **9.5 minutes** |

### DEL 2: Architecture decision

**Decision: daily_snapshots is the sole temporal history system.**

| System | Status | Rationale |
|--------|--------|-----------|
| daily_snapshots | **PRIMARY** | 30.9M rows, 27 days, working |
| trust_score_history | **DEPRECATED** | Renamed to `trust_score_history_deprecated`. Single dump from 2026-02-25, never re-populated. 2.2 GB dead weight. Safe to DROP after 2026-05-14 |
| Freshness snapshots | **RETAINED** | Different purpose: change detection + IndexNow push for top 10K entities. Not a history system |

### DEL 3: Retention policy

**Hierarchical compression (script: `scripts/retention_daily_snapshots.py`):**

| Age | Resolution | Rationale |
|-----|-----------|-----------|
| 0-90 days | Daily | Full granularity for recent analysis |
| 91-365 days | Weekly (Sundays) | Reduces 6/7 of rows |
| >365 days | Monthly (1st of month) | Long-term trends only |

**Storage projections:**

| Scenario | Year 1 | Year 2 | Year 5 |
|----------|--------|--------|--------|
| No retention | 146 GB | 292 GB | 730 GB |
| With retention | ~45 GB | ~55 GB | ~75 GB |

Not needed yet (all data <30 days old). Will activate via monthly LaunchAgent when data reaches 90+ days.

### DEL 4: API endpoint

**GET /api/v1/trust-score/{agent_id}/history**

Returns trust score trajectory from daily_snapshots.

Query parameters:
- `days` — lookback period (default: 30, max: 365)
- `resolution` — `daily` (default), `weekly`, or `monthly`

Response:
```json
{
  "agent_id": "uuid",
  "name": "example/agent",
  "resolution": "daily",
  "days": 30,
  "data_points": 27,
  "history": [
    {"date": "2026-03-19", "trust_score": 85.2, "trust_grade": "A", "downloads": 1234, "stars": 567},
    ...
  ],
  "meta": {
    "source": "Nerq.ai",
    "methodology": "https://nerq.ai/methodology",
    "note": "Trust scores are snapshots — daily values reflect the score at time of collection"
  }
}
```

Caching: `Cache-Control: public, max-age=3600` (1 hour).

MCP tools can call this endpoint directly — no separate tool registration needed.

## What to monitor

1. **LaunchAgent health**: `launchctl list com.nerq.signal-warehouse` — should show `LastExitStatus = 0`
2. **Daily row counts**: Should be ~2.5M/day (software) + ~100K (agents) + ~30K (websites) = ~2.6M/day
3. **Table size**: Currently 9.1 GB for 27 days. Alert if >50 GB before retention kicks in
4. **Trust changes**: Should detect ~300-500 changes/day. 0 = broken
5. **Retention**: Run `python3 scripts/retention_daily_snapshots.py --status` monthly

## Files modified

- `Library/LaunchAgents/com.nerq.signal-warehouse.plist` — added DATABASE_URL
- `agentindex/intelligence/daily_snapshot.py` — batched agents, 300s timeout, resilient collectors
- `agentindex/seo_pages.py` — added `/api/v1/trust-score/{id}/history` endpoint
- `scripts/retention_daily_snapshots.py` — new retention policy script
