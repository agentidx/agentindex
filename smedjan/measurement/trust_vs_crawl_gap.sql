-- Smedjan measurement — top-N trust_score_v2 × AI-bot crawl-surface gap.
--
-- Source: FU-CITATION-20260422-03 (AUDIT-CITATION-20260422, Finding 3,
-- CRITICAL). Top-1000 trust_score_v2 entities present in the top-2000
-- AI-bot-crawled slugs collapsed from 31 → 12 WoW (-61%). This view
-- exposes the gap in both a 7d and a 30d window, and includes the
-- prior-comparable window so a single SELECT tells you which direction
-- the gap is moving.
--
-- Complements ``smedjan.trust_score_crawl_coverage_30d``
-- (FU-CITATION-20260418-03), which was threshold-based
-- (trust_score_v2 >= 80, 24 slugs today). The audit framing is
-- rank-based — "top-N trust × crawled slugs" — so we need the full
-- top-1000 inventory, not just the A-/A/A+ band.
--
-- Applied via:
--   /opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
--     -h smedjan -U smedjan_app -d smedjan \
--     -f ~/agentindex-factory/smedjan/measurement/trust_vs_crawl_gap.sql
-- Idempotent (CREATE … IF NOT EXISTS / CREATE OR REPLACE VIEW).
--
-- Refresh model:
--   * `smedjan.trust_score_top_n_snapshot` — populated by
--     `smedjan.measurement.trust_vs_crawl_gap_refresh` on a nightly
--     schedule from the Nerq RO replica (cross-DB, cannot live in a view).
--   * `smedjan.sitemap_entity_snapshot` — populated by the same refresh
--     script from live nerq.ai /sitemap-safe-*, /sitemap-mcp, /sitemap-agents-*
--     chunks; this is how we diagnose "in sitemap?" without re-fetching
--     per-query. Sitemap fetch is HTTP; running it in a view is not an option.
--   * `smedjan.trust_vs_crawl_gap` — live view, re-aggregates
--     `analytics_mirror.requests` on every SELECT. Cheap because the
--     slug-extraction regex is shared with the existing 30d coverage view
--     and the mirror has `idx_amp_req_ai_bot (is_ai_bot, ts)`.

-- ── Snapshot: top-N trust slugs (rank-based, not threshold-based) ──
-- One row per top-N entity from public.entity_lookup on the Nerq RO
-- replica, ordered by trust_score_v2 DESC. ``trust_rank`` is 1-based.
-- N (default 1000) is controlled by the refresh script; this table
-- simply stores whatever the refresh decided.
CREATE TABLE IF NOT EXISTS smedjan.trust_score_top_n_snapshot (
    trust_rank      integer     NOT NULL,
    slug            text        NOT NULL,
    trust_score_v2  real        NOT NULL,
    trust_grade     text,
    category        text,
    source          text,
    snapshot_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trust_rank, slug)
);

CREATE INDEX IF NOT EXISTS idx_trust_top_n_slug
    ON smedjan.trust_score_top_n_snapshot (slug);

CREATE INDEX IF NOT EXISTS idx_trust_top_n_rank
    ON smedjan.trust_score_top_n_snapshot (trust_rank);

COMMENT ON TABLE smedjan.trust_score_top_n_snapshot IS
  'FU-CITATION-20260422-03: top-N (default 1000) trust_score_v2 slugs from Nerq RO, refreshed nightly. trust_rank is 1-based.';

-- ── Snapshot: entity sitemap membership ──────────────────────────────
-- Captures which slug-families are advertised in the live nerq.ai
-- sitemap. Populated by the refresh script, which fetches
-- /sitemap-safe-{0..5}.xml, /sitemap-agents-{0..5}.xml and /sitemap-mcp.xml
-- and extracts slug paths. Used to diagnose whether a top-trust slug
-- is discoverable via sitemap at all — the audit's root-cause work
-- showed 850/980 top-trust slugs are not in any entity sitemap today.
CREATE TABLE IF NOT EXISTS smedjan.sitemap_entity_snapshot (
    slug             text        NOT NULL,
    sitemap_family   text        NOT NULL,   -- 'safe' | 'agent' | 'mcp'
    snapshot_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (slug, sitemap_family)
);

CREATE INDEX IF NOT EXISTS idx_sitemap_entity_slug
    ON smedjan.sitemap_entity_snapshot (slug);

COMMENT ON TABLE smedjan.sitemap_entity_snapshot IS
  'FU-CITATION-20260422-03: live nerq.ai entity-sitemap membership snapshot. Refreshed nightly alongside trust_score_top_n_snapshot.';

-- ── View: trust × crawl gap, 7d and 30d, with prior-window deltas ────
-- Per top-N slug:
--   ai_bot_crawls_7d        — crawls in the trailing 7d window
--   ai_bot_crawls_prior_7d  — crawls in the 7d window immediately before
--   ai_bot_crawls_30d       — crawls in the trailing 30d window
--   ai_bot_crawls_prior_30d — crawls in the 30d window immediately before
--   in_sitemap              — boolean; slug is in any entity sitemap
--   has_coverage_7d         — boolean; ai_bot_crawls_7d > 0
--   has_coverage_30d        — boolean; ai_bot_crawls_30d > 0
--   coverage_delta_7d       — signed change vs prior 7d (NULL → number
--                             signals emergence; number → NULL signals loss)
--
-- Entity URL families matched: /agent/, /safe/, /model/, /dataset/,
-- /package/, /npm/, /pypi/, /mcp/ (identical to
-- smedjan.trust_score_crawl_coverage_30d for consistency).
CREATE OR REPLACE VIEW smedjan.trust_vs_crawl_gap AS
WITH
crawl_7d AS (
    SELECT substring(path from '^/[a-z]+/([^/?#]+)') AS slug,
           count(*) AS hits
      FROM analytics_mirror.requests
     WHERE is_ai_bot = 1
       AND ts >= now() - interval '7 days'
       AND path ~ '^/(agent|safe|model|dataset|package|npm|pypi|mcp)/[^/?#]+'
     GROUP BY 1
),
crawl_prior_7d AS (
    SELECT substring(path from '^/[a-z]+/([^/?#]+)') AS slug,
           count(*) AS hits
      FROM analytics_mirror.requests
     WHERE is_ai_bot = 1
       AND ts >= now() - interval '14 days'
       AND ts <  now() - interval '7 days'
       AND path ~ '^/(agent|safe|model|dataset|package|npm|pypi|mcp)/[^/?#]+'
     GROUP BY 1
),
crawl_30d AS (
    SELECT substring(path from '^/[a-z]+/([^/?#]+)') AS slug,
           count(*) AS hits
      FROM analytics_mirror.requests
     WHERE is_ai_bot = 1
       AND ts >= now() - interval '30 days'
       AND path ~ '^/(agent|safe|model|dataset|package|npm|pypi|mcp)/[^/?#]+'
     GROUP BY 1
),
crawl_prior_30d AS (
    SELECT substring(path from '^/[a-z]+/([^/?#]+)') AS slug,
           count(*) AS hits
      FROM analytics_mirror.requests
     WHERE is_ai_bot = 1
       AND ts >= now() - interval '60 days'
       AND ts <  now() - interval '30 days'
       AND path ~ '^/(agent|safe|model|dataset|package|npm|pypi|mcp)/[^/?#]+'
     GROUP BY 1
),
sitemap_agg AS (
    SELECT slug, true AS in_sitemap
      FROM smedjan.sitemap_entity_snapshot
     GROUP BY slug
)
SELECT
    t.trust_rank,
    t.slug,
    t.trust_score_v2,
    t.trust_grade,
    t.category,
    t.source,
    coalesce(c7.hits, 0)::bigint  AS ai_bot_crawls_7d,
    coalesce(cp7.hits, 0)::bigint AS ai_bot_crawls_prior_7d,
    coalesce(c30.hits, 0)::bigint AS ai_bot_crawls_30d,
    coalesce(cp30.hits, 0)::bigint AS ai_bot_crawls_prior_30d,
    coalesce(sm.in_sitemap, false) AS in_sitemap,
    (coalesce(c7.hits, 0) > 0)  AS has_coverage_7d,
    (coalesce(c30.hits, 0) > 0) AS has_coverage_30d,
    (coalesce(c7.hits, 0)  - coalesce(cp7.hits, 0))::bigint  AS coverage_delta_7d,
    (coalesce(c30.hits, 0) - coalesce(cp30.hits, 0))::bigint AS coverage_delta_30d,
    t.snapshot_at AS trust_snapshot_at
  FROM smedjan.trust_score_top_n_snapshot t
  LEFT JOIN crawl_7d        c7  ON c7.slug  = t.slug
  LEFT JOIN crawl_prior_7d  cp7 ON cp7.slug = t.slug
  LEFT JOIN crawl_30d       c30 ON c30.slug = t.slug
  LEFT JOIN crawl_prior_30d cp30 ON cp30.slug = t.slug
  LEFT JOIN sitemap_agg     sm  ON sm.slug   = t.slug;

COMMENT ON VIEW smedjan.trust_vs_crawl_gap IS
  'FU-CITATION-20260422-03: top-N trust × AI-bot crawl surface, both 7d and 30d, with prior-window deltas for WoW alerting and sitemap-membership diagnosis.';

-- ── View: summary for WoW alerting ───────────────────────────────────
-- Single-row rollup suitable for a Buzz / healthcheck scrape. The
-- `gap_grew_wow` booleans trip when the top-N invisible count (=
-- has_coverage_* = false) grew week-over-week (30d window) or the
-- 7d slice dropped vs the prior 7d.
CREATE OR REPLACE VIEW smedjan.trust_vs_crawl_gap_summary AS
WITH
top_n AS (
    SELECT count(*) AS n FROM smedjan.trust_score_top_n_snapshot
),
covered AS (
    SELECT
        count(*) FILTER (WHERE has_coverage_7d)        AS covered_7d,
        count(*) FILTER (WHERE ai_bot_crawls_prior_7d > 0)  AS covered_prior_7d,
        count(*) FILTER (WHERE has_coverage_30d)       AS covered_30d,
        count(*) FILTER (WHERE ai_bot_crawls_prior_30d > 0) AS covered_prior_30d,
        count(*) FILTER (WHERE in_sitemap)             AS in_sitemap_count,
        count(*)                                       AS top_n
      FROM smedjan.trust_vs_crawl_gap
)
SELECT
    top_n,
    covered_7d,
    covered_prior_7d,
    (covered_prior_7d  - covered_7d)                           AS gap_delta_7d,
    covered_30d,
    covered_prior_30d,
    (covered_prior_30d - covered_30d)                          AS gap_delta_30d,
    in_sitemap_count,
    (top_n - in_sitemap_count)                                 AS missing_from_sitemap,
    ((covered_prior_30d - covered_30d) > 0)                    AS gap_grew_wow_30d,
    ((covered_prior_7d  - covered_7d ) > 0)                    AS gap_grew_wow_7d,
    now()                                                      AS computed_at
  FROM covered;

COMMENT ON VIEW smedjan.trust_vs_crawl_gap_summary IS
  'FU-CITATION-20260422-03: single-row rollup of trust_vs_crawl_gap with WoW alert booleans. gap_grew_wow_* = true fires the citation-health alert.';
