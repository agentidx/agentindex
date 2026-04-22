-- Smedjan measurement — crawl-to-cited ratio, daily × bot_purpose.
--
-- Source: FU-CITATION-20260422-01 (AUDIT-CITATION-20260422, Finding 1,
-- critical) promotes "crawl-to-cited ratio" to the citation workstream's
-- North Star KPI. Ingestion saturated at ~5.3M AI-bot hits/30d while
-- ai_mediated visits held flat at ~36.7K, so week-over-week changes in
-- ratio — not raw crawl volume — are the signal that matters.
--
-- Finding 10 (bot_purpose split) showed user_triggered crawls track
-- ai_mediated visits nearly 1:1, while training traffic (94% of volume)
-- dilutes the headline number. The view therefore carries a per-
-- bot_purpose row plus a rollup row (bot_purpose = 'all') so the weekly
-- audit and Buzz report can quote both the global ratio and the yield
-- by purpose without joining twice.
--
-- Applied via:
--   set -a; . ~/smedjan/config/.env; set +a
--   PGPASSWORD=$SMEDJAN_APP_PW \
--     /opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
--       -h smedjan -U smedjan_app -d smedjan \
--       -f ~/agentindex/smedjan/measurement/citation_ratio_daily.sql
-- Idempotent (CREATE OR REPLACE VIEW).
--
-- ai_mediated visits have no bot_purpose column — they are human clicks,
-- not bot hits — so the denominator is the daily ai_mediated total. The
-- same daily `ai_mediated` value is repeated across the per-purpose rows.
-- Always filter `bot_purpose = 'all'` when summing `ai_mediated` to avoid
-- triple-counting.

CREATE OR REPLACE VIEW analytics_mirror.citation_ratio_daily AS
WITH crawls_by_purpose AS (
    SELECT (ts AT TIME ZONE 'UTC')::date AS day,
           coalesce(bot_purpose, '(unknown)') AS bot_purpose,
           count(*)::bigint                   AS crawls
      FROM analytics_mirror.requests
     WHERE is_ai_bot = 1
     GROUP BY 1, 2
),
crawls_all AS (
    SELECT (ts AT TIME ZONE 'UTC')::date AS day,
           'all'::text                   AS bot_purpose,
           count(*)::bigint              AS crawls
      FROM analytics_mirror.requests
     WHERE is_ai_bot = 1
     GROUP BY 1
),
crawls AS (
    SELECT * FROM crawls_by_purpose
    UNION ALL
    SELECT * FROM crawls_all
),
mediated AS (
    SELECT (ts AT TIME ZONE 'UTC')::date AS day,
           count(*)::bigint              AS ai_mediated
      FROM analytics_mirror.requests
     WHERE visitor_type = 'ai_mediated'
     GROUP BY 1
)
SELECT
    c.day,
    c.bot_purpose,
    c.crawls,
    coalesce(m.ai_mediated, 0)::bigint AS ai_mediated,
    CASE
        WHEN coalesce(m.ai_mediated, 0) = 0 THEN NULL
        ELSE round(c.crawls::numeric / m.ai_mediated, 2)
    END AS ratio
  FROM crawls c
  LEFT JOIN mediated m USING (day);

COMMENT ON VIEW analytics_mirror.citation_ratio_daily IS
  'FU-CITATION-20260422-01: North Star KPI — AI-bot crawls ÷ ai_mediated visits, per day × bot_purpose with an all-purposes rollup. Filter bot_purpose=''all'' for the global ratio; filter bot_purpose=''user_triggered'' for the real-time yield signal from F10.';
