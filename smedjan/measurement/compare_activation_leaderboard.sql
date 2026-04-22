-- Smedjan measurement — /compare/X-vs-Y activation leaderboard.
--
-- Source: FU-CITATION-20260422-06 (AUDIT-CITATION-20260422, Finding 6, medium).
-- The citation audit found the /compare/ template activates only 2.0% of
-- crawled slugs (1,493 cited / 74,161 crawled over 30d). The prior plan to
-- ship +10K /compare/ pages assumed linear yield; the data shows a long
-- tail under 2%. This view ranks existing /compare/X-vs-Y pairs by an
-- activation score so the generator can prioritise clones/variants of
-- proven-yield pairs instead of enumerating all permutations.
--
-- Scoring
-- -------
-- score = smoothed_ratio * age_weight
--   smoothed_ratio = ai_mediated_7d / (bot_7d + SMOOTHING_K)
--   age_weight     = 1 - exp(-slug_age_days / AGE_TAU)
--
-- Smoothing pulls low-evidence pairs (e.g. 1 bot / 1 mediated) toward
-- zero so a single coincidental click can't top the leaderboard; a pair
-- needs sustained volume to win. Age weighting dampens brand-new URLs
-- that haven't had time to accumulate reliable signal yet.
--
-- Constants (keep in sync with the refresh script and the generator):
--   SMOOTHING_K = 10    -- "add 10 virtual bot hits with 0 activation"
--   AGE_TAU     = 14    -- days; weight reaches ~0.63 at 14d, ~0.95 at 42d
--
-- Applied via:
--   /opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
--     -h smedjan -U smedjan_app -d smedjan \
--     -f ~/agentindex/smedjan/measurement/compare_activation_leaderboard.sql
-- Idempotent (CREATE OR REPLACE VIEW / CREATE TABLE IF NOT EXISTS).

-- ── Priority-queue snapshot table ────────────────────────────────────────
-- The view below is LIVE (re-aggregates requests on every SELECT). This
-- table is a point-in-time top-decile snapshot that the generator reads
-- as a cheap JSON export — written by
-- `smedjan.measurement.compare_activation_refresh`. Keeping the snapshot
-- in the smedjan DB (rather than only on disk) makes the priority set
-- auditable from psql and survives Mac-Studio filesystem loss.
CREATE TABLE IF NOT EXISTS smedjan.compare_priority_queue (
    pair_slug           text        PRIMARY KEY,
    slug_a              text        NOT NULL,
    slug_b              text        NOT NULL,
    bot_7d              integer     NOT NULL,
    ai_mediated_7d      integer     NOT NULL,
    raw_activation_ratio double precision,
    slug_age_days       real,
    activation_score    double precision NOT NULL,
    activation_rank     integer     NOT NULL,
    snapshot_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_compare_priority_queue_rank
    ON smedjan.compare_priority_queue (activation_rank ASC);

COMMENT ON TABLE smedjan.compare_priority_queue IS
  'FU-CITATION-20260422-06: top-decile /compare/ pairs by activation_score, refreshed daily. Feeds agentindex/intelligence/comparison_generator as a priority queue.';

-- ── View: compare_activation_leaderboard ─────────────────────────────────
-- One row per /compare/<slug_a>-vs-<slug_b> path seen in the last 7 days
-- (bot or human), ordered by activation_score.
--
-- Columns:
--   pair_slug             — the full <a>-vs-<b> slug (URL path tail)
--   slug_a, slug_b        — split on the first '-vs-' substring; note that
--                           slugs may themselves contain '-' which makes
--                           split_part greedy on both ends. Consumers that
--                           need exact slug identity should join back to
--                           software_registry on either half independently.
--   bot_7d                — is_ai_bot=1 request count, last 7d
--   ai_mediated_7d        — visitor_type='ai_mediated' count, last 7d
--   raw_activation_ratio  — ai_mediated_7d / bot_7d (NULL if bot_7d=0).
--                           Unsmoothed — treat as a raw observation, not
--                           a ranking key.
--   slug_age_days         — days since the pair's first observed request
--                           within a 30d window (≈30 means "old enough",
--                           < 14 means "young, treat with caution").
--   activation_score      — smoothed_ratio * age_weight (see top of file).
--                           Always ≥ 0. This is the ranking key.
--   activation_rank       — 1 = most-activated pair, ties broken by
--                           higher ai_mediated_7d then lower bot_7d.
--
-- Filters:
--   * pair_slug LIKE '%-vs-%' — excludes bare /compare/ hub hits and
--     single-slug paths like /compare/knowledge which aren't X-vs-Y.
--   * bot_7d >= 1 — pairs that never saw a bot hit in 7d have nothing to
--     say about activation; they belong in inventory-expansion not
--     prioritisation.
CREATE OR REPLACE VIEW smedjan.compare_activation_leaderboard AS
WITH compare_7d AS (
    SELECT
        substring(path from '^/compare/([^/?#]+)')          AS pair_slug,
        count(*) FILTER (WHERE is_ai_bot = 1)               AS bot_7d,
        count(*) FILTER (WHERE visitor_type = 'ai_mediated') AS ai_mediated_7d
      FROM analytics_mirror.requests
     WHERE ts >= now() - interval '7 days'
       AND path LIKE '/compare/%'
     GROUP BY 1
),
compare_age AS (
    SELECT
        substring(path from '^/compare/([^/?#]+)')          AS pair_slug,
        min(ts)                                             AS first_seen_ts_30d
      FROM analytics_mirror.requests
     WHERE ts >= now() - interval '30 days'
       AND path LIKE '/compare/%'
     GROUP BY 1
),
scored AS (
    SELECT
        h.pair_slug,
        h.bot_7d,
        h.ai_mediated_7d,
        CASE WHEN h.bot_7d = 0 THEN NULL
             ELSE h.ai_mediated_7d::double precision / h.bot_7d::double precision
        END                                                  AS raw_activation_ratio,
        (EXTRACT(EPOCH FROM (now() - a.first_seen_ts_30d)) / 86400.0)::real AS slug_age_days,
        (h.ai_mediated_7d::double precision / (h.bot_7d + 10.0))
          * (1.0 - EXP(-EXTRACT(EPOCH FROM (now() - a.first_seen_ts_30d)) / 86400.0 / 14.0))
                                                             AS activation_score
      FROM compare_7d h
      LEFT JOIN compare_age a USING (pair_slug)
     WHERE h.pair_slug LIKE '%-vs-%'
       AND h.bot_7d >= 1
)
SELECT
    pair_slug,
    split_part(pair_slug, '-vs-', 1)                        AS slug_a,
    split_part(pair_slug, '-vs-', 2)                        AS slug_b,
    bot_7d::integer                                         AS bot_7d,
    ai_mediated_7d::integer                                 AS ai_mediated_7d,
    raw_activation_ratio,
    slug_age_days,
    activation_score,
    rank() OVER (
        ORDER BY activation_score DESC,
                 ai_mediated_7d   DESC,
                 bot_7d           ASC
    )::integer                                              AS activation_rank
  FROM scored;

COMMENT ON VIEW smedjan.compare_activation_leaderboard IS
  'FU-CITATION-20260422-06: /compare/X-vs-Y pairs ranked by smoothed_ratio*age_weight. activation_rank=1 is the highest-yield pair. Feed the top decile into the /compare/ generator as priority.';
