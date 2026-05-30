# Tracking: audit of `lower(col) LIKE` patterns and supporting indexes

**Opened:** 2026-05-30 (after R-SW incident)
**Status:** documenting — proactive fix only when next saturation observed
**Owner:** unassigned

## Why this exists

The 2026-05-30 R-SW incident showed a single `lower(name) LIKE` pattern on
`software_registry` saturated Nbg because the existing btree on
`(registry, lower(name))` didn't use the `text_pattern_ops` opclass. The
incident has been fixed (commit `04ee95e`), but the *class* of bug —
"functional index on a `LIKE` pattern is missing the right opclass" —
could exist on other tables.

This file inventories every `lower(<col>) LIKE` (and `name_lower LIKE`)
callsite plus the index situation on the referenced table.

## Audit findings

### `software_registry` — **FIXED** in commit `04ee95e`

| Property | Value |
|---|---|
| Size | 1.6 GB, 2.9 M rows |
| Callsites |     `agentindex/preflight.py:250` (the R-SW culprit), `agentindex/agent_safety_pages.py:5148`, `agentindex/api/discovery.py:488` |
| Pre-fix indexes | `idx_sr_registry_name` btree on `(registry, lower(name))` — **no LIKE support** |
| Post-fix | `ix_software_registry_registry_lower_name_pattern` btree with `text_pattern_ops` |
| Status | Done. Prefix LIKE now <100 ms (was 65 s). |

**Remaining concern:** `discovery.py:488` queries with `%pat%` (substring,
not prefix). `text_pattern_ops` does NOT support substring LIKE — only
prefix. For substring search on `software_registry.name`, would need a
trigram GIN index, e.g.

```sql
CREATE INDEX CONCURRENTLY ix_sr_name_trgm
    ON software_registry USING gin (lower(name) gin_trgm_ops);
```

Mitigation in place: discovery.py:488 wraps the query in
`SET LOCAL statement_timeout = '3s'`. Self-bounded; can't drive a
saturation incident. Defer the trigram index unless the 3s limit becomes
a UX issue.

### `entity_lookup` — **NO ACTION NEEDED**

| Property | Value |
|---|---|
| Size | 1.9 GB, 5.0 M rows |
| Callsites | 14 files use `name_lower LIKE lower(:pattern)` (intelligence_api, kya_api, mcp_trust_pages, nerq_scout, agent_compare_pages, badge_api, economics_api, claim_page, seo_trust_pages, review_pages, etc.) |
| Indexes | `idx_el_name_trgm` GIN on `name_lower` with `gin_trgm_ops` ✓ |
| | `idx_el_name_lower` btree on `name_lower` (equality lookups) ✓ |
| Status | Indexes cover prefix LIKE, substring LIKE, and case-insensitive variants via the trigram GIN. Verified by EXPLAIN ANALYZE: prefix LIKE 36 ms, substring LIKE 37 ms. |

This is the model coverage. Future tables that need `LIKE` should match
this pattern (btree for equality, GIN trigram for fuzzy / pattern).

### `software_registry.slug` — minor concern

`discovery.py:488` queries `lower(slug) LIKE lower(:pat)`. The
`software_registry_registry_slug_key` index is on `(registry, slug)`
without `lower()` or `text_pattern_ops` → won't help LIKE on lower(slug).

Slug values are short and unique within registry. Even a full scan of
2.9M rows on a short text column finishes well inside the
`statement_timeout = '3s'` guard. Not blocking; left as-is.

### Other patterns inspected

- `ILIKE` callsites in `mcp_sse_server_v2.py`, `mcp_server_v2.py`,
  `smart_discovery.py`, `comparison_pages.py` — all query
  `entity_lookup`; covered by the trigram GIN above.
- `lower(replace(replace(name, ' ', ''), '-', ''))` lookups in
  agent_safety_pages.py — `software_registry` has
  `idx_sr_name_normalized` (functional btree on the exact normalized
  expression). Adequate for equality `=`; not for LIKE. No LIKE
  callsite uses this expression.
- `lower(author)` lookups — `software_registry` has `idx_sr_author_lower`.
  No LIKE callsites observed.

## Action criteria — when to revisit

Open a follow-up fix only when one of these happens:

1. `infrastructure_alerts` shows a `SLOW_QUERY` or `SLOW_TRENDING` alert
   targeting `agentindex_write` for >30 minutes sustained.
2. `pg_stat_activity` snapshot shows ≥2 concurrent queries on a single
   table running >5 s — sign of saturation building.
3. An app-level page surfaces a slow response over the suite's 8 s
   ceiling that maps to a `lower(col) LIKE` pattern not covered above.

Until then, the post-STEP-2 index coverage is sufficient.

## Related

- R-SW root cause + STEP 2 fix: `docs/status/r7_state_check_20260530_1735.md`
- Migration: `migrations/public/20260530-02-software-registry-lower-name-pattern-index.sql`
- Healthcheck that catches recurrence: `scripts/infra_healthcheck.py`
  (post-STEP 3 with SELECT 1 + slow-trend layers).
