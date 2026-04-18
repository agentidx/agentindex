-- Smedjan analytics-mirror schema — applied to the smedjan DB on
-- smedjan.nbg1.hetzner. Populated nightly by
-- scripts/smedjan-analytics-export.sh (Mac Studio) + import counterpart
-- on smedjan.
--
-- Filter used on `requests`:
--   WHERE is_ai_bot = 1
--      OR path LIKE '/safe/%'
--      OR path LIKE '/compare/%'
--      OR path LIKE '/best/%'
--      OR path LIKE '/alternatives/%'
--      OR status >= 400
--
-- Retention: last 30 days of preflight_analytics + requests; full copy
-- of requests_daily. Rebuild model (TRUNCATE + COPY) — no delta upsert.

CREATE SCHEMA IF NOT EXISTS analytics_mirror;
ALTER SCHEMA analytics_mirror OWNER TO smedjan_app;

-- Sync tracker — one row keyed by table name, updated by the importer.
CREATE TABLE IF NOT EXISTS analytics_mirror._sync_state (
    table_name   text PRIMARY KEY,
    row_count    bigint NOT NULL,
    synced_at    timestamptz NOT NULL DEFAULT now(),
    source_host  text,
    source_hash  text,
    notes        text
);

-- preflight_analytics mirror (SQLite types mapped to Postgres).
CREATE TABLE IF NOT EXISTS analytics_mirror.preflight_analytics (
    id            bigint PRIMARY KEY,
    ts            timestamptz NOT NULL,
    target        text,
    bot_name      text,
    ip            text,
    status        integer,
    duration_ms   double precision,
    country       text
);
CREATE INDEX IF NOT EXISTS idx_amp_pa_ts
    ON analytics_mirror.preflight_analytics (ts);
CREATE INDEX IF NOT EXISTS idx_amp_pa_target
    ON analytics_mirror.preflight_analytics (target);

-- requests mirror (filtered subset).
CREATE TABLE IF NOT EXISTS analytics_mirror.requests (
    id               bigint PRIMARY KEY,
    ts               timestamptz NOT NULL,
    method           text,
    path             text,
    status           integer,
    duration_ms      double precision,
    ip               text,
    user_agent       text,
    bot_name         text,
    is_bot           integer,
    is_ai_bot        integer,
    referrer         text,
    referrer_domain  text,
    query_string     text,
    search_query     text,
    country          text,
    ai_source        text,
    visitor_type     text,
    bot_purpose      text
);
CREATE INDEX IF NOT EXISTS idx_amp_req_ts
    ON analytics_mirror.requests (ts);
CREATE INDEX IF NOT EXISTS idx_amp_req_path_ts
    ON analytics_mirror.requests (path, ts);
CREATE INDEX IF NOT EXISTS idx_amp_req_ai_bot
    ON analytics_mirror.requests (is_ai_bot, ts);
CREATE INDEX IF NOT EXISTS idx_amp_req_status_ts
    ON analytics_mirror.requests (status, ts);

-- requests_daily aggregate (full copy, small).
CREATE TABLE IF NOT EXISTS analytics_mirror.requests_daily (
    day           date NOT NULL,
    bot_name      text,
    is_ai_bot     integer,
    is_bot        integer,
    status        integer,
    is_gptbot     integer,
    is_preflight  integer,
    visitor_type  text,
    country       text,
    lang          text,
    count         bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_amp_rd_day
    ON analytics_mirror.requests_daily (day);
CREATE INDEX IF NOT EXISTS idx_amp_rd_ai_bot_day
    ON analytics_mirror.requests_daily (is_ai_bot, day);

-- ai_demand_scores — MOVES from agentindex.public to smedjan.smedjan
-- in M10. Create it here so the M10 data load has a target, and so
-- scripts that import smedjan.config at build time don't break while
-- M10 is still in flight.
CREATE TABLE IF NOT EXISTS smedjan.ai_demand_scores (
    slug              text PRIMARY KEY,
    score             real NOT NULL,
    last_30d_queries  integer NOT NULL,
    computed_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ai_demand_scores_score
    ON smedjan.ai_demand_scores (score DESC);
CREATE INDEX IF NOT EXISTS idx_ai_demand_scores_computed_at
    ON smedjan.ai_demand_scores (computed_at);
