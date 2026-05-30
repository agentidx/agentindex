-- 2026-05-30 R-SW STEP 2: functional index on software_registry for LIKE scans.
-- Context: r7_state_check_20260530_1735.md identified 5 concurrent
-- 65-second queries of the form
--   WHERE registry = :reg AND lower(name) LIKE lower(:pat)
-- saturating Nbg PG. There's already a btree on (registry, lower(name))
-- but the default opclass doesn't support LIKE — only equality and range.
-- Adding the text_pattern_ops variant.
--
-- IMPORTANT: This DDL uses CREATE INDEX CONCURRENTLY, which CANNOT run
-- inside a transaction block. Apply with:
--   psql -d agentindex -h 100.119.193.70 -v ON_ERROR_STOP=1 -f <thisfile>
-- The psql client treats each statement independently in the absence of
-- BEGIN/COMMIT.
--
-- Bypass PgBouncer for this one (query_timeout=60 in pgbouncer.ini would
-- kill the index build mid-flight on a 2.9M-row table).
--
-- Idempotent: yes (CREATE INDEX CONCURRENTLY IF NOT EXISTS).

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_software_registry_registry_lower_name_pattern
    ON public.software_registry (registry, lower(name) text_pattern_ops);


-- Verify:
--   \d+ software_registry
--   EXPLAIN ANALYZE SELECT id FROM software_registry
--     WHERE registry='npm' AND lower(name) LIKE 'react%';
-- Expected: Bitmap Index Scan on ix_software_registry_registry_lower_name_pattern
-- Expected runtime: <100ms (was 65s+)


-- DOWN (manual, requires CONCURRENTLY for online removal):
--   DROP INDEX CONCURRENTLY IF EXISTS public.ix_software_registry_registry_lower_name_pattern;
