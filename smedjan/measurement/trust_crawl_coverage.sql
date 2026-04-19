-- Smedjan measurement — trust-score × AI-bot crawl-coverage cross-check.
--
-- Source: FU-CITATION-20260418-03 (AUDIT-CITATION-20260418, Finding 3, high).
-- The citation audit found that only 31 of the top-1000 trust_score_v2
-- entities appear in the top-2000 AI-bot-crawled paths over 30d. This
-- schema closes that loop programmatically: a nightly snapshot of
-- high-trust entities from the Nerq RO replica, joined against the
-- analytics_mirror 30d AI-bot-crawl aggregation, with the bottom decile
-- (lowest crawl coverage) surfaced for the F3 internal-linking generator.
--
-- Applied via:
--   /opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
--     -h smedjan -U smedjan_app -d smedjan \
--     -f ~/agentindex/smedjan/measurement/trust_crawl_coverage.sql
-- Idempotent (CREATE ... IF NOT EXISTS / CREATE OR REPLACE VIEW).
--
-- Refresh model: `smedjan.measurement.trust_crawl_coverage_refresh` pulls
-- from Nerq RO into `smedjan.trust_score_snapshot` on a nightly schedule.
-- The view below is LIVE — every SELECT re-aggregates analytics_mirror.
-- The snapshot table exists because Nerq RO is a separate database; a
-- cross-DB LEFT JOIN cannot be expressed as a single view.

-- ── Snapshot table ────────────────────────────────────────────────────────
-- One row per active Nerq entity with trust_score_v2 >= 80 (A-, A, A+).
-- Populated by the refresh job from public.entity_lookup on the Nerq RO
-- replica. The LIMIT threshold here must stay in sync with the refresh
-- job (see trust_crawl_coverage_refresh.TRUST_SCORE_MIN).
CREATE TABLE IF NOT EXISTS smedjan.trust_score_snapshot (
    slug            text        PRIMARY KEY,
    trust_score_v2  real        NOT NULL,
    trust_grade     text,
    category        text,
    snapshot_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trust_score_snapshot_score
    ON smedjan.trust_score_snapshot (trust_score_v2 DESC);

-- ── View: 30d AI-bot crawl coverage for high-trust slugs ─────────────────
-- Columns (per the FU-CITATION-20260418-03 spec):
--   slug                — entity slug from Nerq RO snapshot
--   trust_score_v2      — real, >= 80
--   trust_grade         — A- / A / A+
--   ai_bot_crawls_30d   — count of is_ai_bot=1 requests to any entity
--                         page matching the slug over the last 30 days
--                         (0 if the slug has never been crawled)
--   coverage_gap_rank   — 1 = lowest crawl coverage (biggest gap);
--                         ties broken by higher trust_score_v2 first
--
-- Path families matched: /agent/, /safe/, /model/, /dataset/, /package/,
-- /npm/, /pypi/, /mcp/. These are the entity-page prefixes the citation
-- audit inventoried. Localised language prefixes (/de/, /sv/, …) are NOT
-- counted — this view measures canonical-URL crawl coverage.
CREATE OR REPLACE VIEW smedjan.trust_score_crawl_coverage_30d AS
WITH crawls AS (
    SELECT substring(path from '^/[a-z]+/([^/?#]+)') AS slug,
           count(*)                                   AS ai_bot_crawls_30d
      FROM analytics_mirror.requests
     WHERE is_ai_bot = 1
       AND ts >= now() - interval '30 days'
       AND path ~ '^/(agent|safe|model|dataset|package|npm|pypi|mcp)/[^/?#]+'
     GROUP BY 1
)
SELECT
    s.slug,
    s.trust_score_v2,
    s.trust_grade,
    s.category,
    coalesce(c.ai_bot_crawls_30d, 0)::bigint AS ai_bot_crawls_30d,
    rank() OVER (
        ORDER BY coalesce(c.ai_bot_crawls_30d, 0) ASC,
                 s.trust_score_v2 DESC
    ) AS coverage_gap_rank
  FROM smedjan.trust_score_snapshot s
  LEFT JOIN crawls c ON c.slug = s.slug
 WHERE s.trust_score_v2 >= 80;

COMMENT ON VIEW smedjan.trust_score_crawl_coverage_30d IS
  'FU-CITATION-20260418-03: high-trust entities joined with 30d AI-bot crawl volume; coverage_gap_rank=1 is the single most-invisible high-trust slug.';

COMMENT ON COLUMN smedjan.trust_score_snapshot.slug IS
  'Primary key; matches public.entity_lookup.slug on the Nerq RO replica.';
