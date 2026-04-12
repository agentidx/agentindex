-- ZARQ Tier A migration: SQLite -> PostgreSQL DDL
-- Generated 2026-04-12 from crypto_trust.db schema
-- Target: Mac Studio PostgreSQL 16 (database: agentindex)

-- Safety: use schema 'zarq' to isolate from nerq tables
CREATE SCHEMA IF NOT EXISTS zarq;

CREATE TABLE IF NOT EXISTS zarq.nerq_risk_signals (
  token_id TEXT,
  signal_date TEXT,
  btc_beta DOUBLE PRECISION,
  vol_30d DOUBLE PRECISION,
  trust_p3 DOUBLE PRECISION,
  trust_score DOUBLE PRECISION,
  sig6_structure DOUBLE PRECISION,
  ndd_current DOUBLE PRECISION,
  ndd_min_4w DOUBLE PRECISION,
  p3_decay_3m DOUBLE PRECISION,
  score_decay_3m DOUBLE PRECISION,
  structural_weakness INTEGER,
  structural_strength INTEGER,
  risk_level TEXT,
  drawdown_90d DOUBLE PRECISION,
  weeks_since_ath DOUBLE PRECISION,
  excess_vol DOUBLE PRECISION,
  p3_rank DOUBLE PRECISION,
  details TEXT,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  first_collapse_date TEXT,
  price_at_collapse DOUBLE PRECISION,
  weeks_in_collapse INTEGER,
  PRIMARY KEY (token_id, signal_date)
);

CREATE TABLE IF NOT EXISTS zarq.crypto_ndd_alerts (
  id INTEGER,
  alert_date TEXT NOT NULL,
  token_id TEXT NOT NULL,
  symbol TEXT,
  alert_level TEXT NOT NULL,
  ndd DOUBLE PRECISION NOT NULL,
  market_cap_rank INTEGER,
  trust_grade TEXT,
  trigger_signals TEXT,
  message TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS zarq.crypto_price_history (
  token_id TEXT NOT NULL,
  date TEXT NOT NULL,
  open DOUBLE PRECISION,
  high DOUBLE PRECISION,
  low DOUBLE PRECISION,
  close DOUBLE PRECISION,
  volume DOUBLE PRECISION,
  market_cap DOUBLE PRECISION,
  fetched_at TEXT NOT NULL,
  source TEXT DEFAULT 'coingecko',
  PRIMARY KEY (token_id, date)
);

CREATE TABLE IF NOT EXISTS zarq.external_trust_signals (
  id INTEGER,
  agent_name TEXT NOT NULL,
  source TEXT NOT NULL,
  signal_name TEXT NOT NULL,
  signal_value DOUBLE PRECISION,
  signal_max DOUBLE PRECISION,
  raw_data TEXT,
  fetched_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS zarq.compatibility_matrix (
  agent_a TEXT NOT NULL,
  agent_b TEXT NOT NULL,
  compatibility_score DOUBLE PRECISION NOT NULL,
  compatibility_type TEXT NOT NULL,
  evidence TEXT,
  updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  PRIMARY KEY (agent_a, agent_b, compatibility_type)
);

CREATE TABLE IF NOT EXISTS zarq.chain_dex_volumes (
  chain TEXT,
  daily_volume DOUBLE PRECISION,
  weekly_volume DOUBLE PRECISION,
  monthly_volume DOUBLE PRECISION,
  daily_fees DOUBLE PRECISION,
  fetched_at TEXT,
  PRIMARY KEY (chain)
);

CREATE TABLE IF NOT EXISTS zarq.crypto_pipeline_runs (
  id INTEGER,
  run_date TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  steps_json TEXT,
  status TEXT,
  total_seconds DOUBLE PRECISION,
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS zarq.agent_dashboard (
  agent_name TEXT,
  trust_score_history TEXT,
  preflight_checks_7d INTEGER DEFAULT 0,
  preflight_checks_30d INTEGER DEFAULT 0,
  page_views_7d INTEGER DEFAULT 0,
  badge_displays_7d INTEGER DEFAULT 0,
  category_rank INTEGER,
  category_total INTEGER,
  category_avg_trust DOUBLE PRECISION,
  updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  PRIMARY KEY (agent_name)
);

CREATE TABLE IF NOT EXISTS zarq.crypto_ndd_daily (
  id INTEGER,
  run_date TEXT NOT NULL,
  token_id TEXT NOT NULL,
  symbol TEXT,
  name TEXT,
  market_cap_rank INTEGER,
  trust_grade TEXT,
  ndd DOUBLE PRECISION NOT NULL,
  signal_1 DOUBLE PRECISION,
  signal_2 DOUBLE PRECISION,
  signal_3 DOUBLE PRECISION,
  signal_4 DOUBLE PRECISION,
  signal_5 DOUBLE PRECISION,
  signal_6 DOUBLE PRECISION,
  signal_7 DOUBLE PRECISION,
  alert_level TEXT,
  override_triggered INTEGER DEFAULT 0,
  confirmed_distress INTEGER DEFAULT 0,
  has_ohlcv INTEGER DEFAULT 0,
  price_usd DOUBLE PRECISION,
  market_cap DOUBLE PRECISION,
  volume_24h DOUBLE PRECISION,
  breakdown TEXT,
  calculated_at TEXT NOT NULL,
  ndd_trend TEXT,
  ndd_change_4w DOUBLE PRECISION,
  crash_probability DOUBLE PRECISION,
  hc_alert INTEGER DEFAULT 0,
  hc_streak INTEGER DEFAULT 0,
  bottlefish_signal TEXT,
  bounce_90d DOUBLE PRECISION,
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS zarq.crypto_rating_daily (
  id INTEGER,
  run_date TEXT NOT NULL,
  token_id TEXT NOT NULL,
  symbol TEXT,
  name TEXT,
  market_cap_rank INTEGER,
  rating TEXT NOT NULL,
  score DOUBLE PRECISION NOT NULL,
  pillar_1 DOUBLE PRECISION,
  pillar_2 DOUBLE PRECISION,
  pillar_3 DOUBLE PRECISION,
  pillar_4 DOUBLE PRECISION,
  pillar_5 DOUBLE PRECISION,
  breakdown TEXT,
  price_usd DOUBLE PRECISION,
  market_cap DOUBLE PRECISION,
  volume_24h DOUBLE PRECISION,
  price_change_24h DOUBLE PRECISION,
  price_change_7d DOUBLE PRECISION,
  price_change_30d DOUBLE PRECISION,
  calculated_at TEXT NOT NULL,
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS zarq.vitality_scores (
  token_id TEXT,
  symbol TEXT,
  name TEXT,
  vitality_score DOUBLE PRECISION,
  vitality_grade TEXT,
  ecosystem_gravity DOUBLE PRECISION,
  capital_commitment DOUBLE PRECISION,
  coordination_efficiency DOUBLE PRECISION,
  stress_resilience DOUBLE PRECISION,
  organic_momentum DOUBLE PRECISION,
  trust_score DOUBLE PRECISION,
  trust_rating TEXT,
  confidence INTEGER,
  data_coverage TEXT,
  computed_at TEXT,
  PRIMARY KEY (token_id)
);

CREATE TABLE IF NOT EXISTS zarq.defi_yields (
  pool_id TEXT NOT NULL,
  chain TEXT,
  project TEXT,
  symbol TEXT,
  tvl_usd DOUBLE PRECISION,
  apy DOUBLE PRECISION,
  apy_base DOUBLE PRECISION,
  apy_reward DOUBLE PRECISION,
  il_risk TEXT,
  stablecoin INTEGER,
  crawled_at TEXT,
  PRIMARY KEY (pool_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_nerq_risk_signals_token_id_signal_date ON zarq.nerq_risk_signals (token_id, signal_date);
CREATE INDEX IF NOT EXISTS idx_crypto_price_history_token_id_date ON zarq.crypto_price_history (token_id, date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_external_trust_signals_agent_name_source_signal_name ON zarq.external_trust_signals (agent_name, source, signal_name);
CREATE INDEX IF NOT EXISTS idx_external_trust_signals_source ON zarq.external_trust_signals (source);
CREATE INDEX IF NOT EXISTS idx_external_trust_signals_agent_name ON zarq.external_trust_signals (agent_name);
CREATE INDEX IF NOT EXISTS idx_compatibility_matrix_agent_b ON zarq.compatibility_matrix (agent_b);
CREATE INDEX IF NOT EXISTS idx_compatibility_matrix_agent_a ON zarq.compatibility_matrix (agent_a);
CREATE INDEX IF NOT EXISTS idx_agent_dashboard_category_rank ON zarq.agent_dashboard (category_rank);
CREATE INDEX IF NOT EXISTS idx_crypto_ndd_daily_run_date_alert_level ON zarq.crypto_ndd_daily (run_date, alert_level);
CREATE INDEX IF NOT EXISTS idx_crypto_ndd_daily_token_id_run_date ON zarq.crypto_ndd_daily (token_id, run_date);
CREATE INDEX IF NOT EXISTS idx_crypto_ndd_daily_run_date ON zarq.crypto_ndd_daily (run_date);
CREATE INDEX IF NOT EXISTS idx_crypto_rating_daily_token_id_run_date ON zarq.crypto_rating_daily (token_id, run_date);
CREATE INDEX IF NOT EXISTS idx_crypto_rating_daily_run_date ON zarq.crypto_rating_daily (run_date);

-- Data volume summary:
-- nerq_risk_signals: 6355 rows, 23 cols, 2 indexes
-- crypto_ndd_alerts: 1530189 rows, 11 cols, 0 indexes
-- crypto_price_history: 1125586 rows, 10 cols, 2 indexes
-- external_trust_signals: 22502 rows, 8 cols, 3 indexes
-- compatibility_matrix: 18741 rows, 6 cols, 3 indexes
-- chain_dex_volumes: 316 rows, 6 cols, 1 indexes
-- crypto_pipeline_runs: 371 rows, 7 cols, 0 indexes
-- agent_dashboard: 15986 rows, 10 cols, 2 indexes
-- crypto_ndd_daily: 230412 rows, 31 cols, 4 indexes
-- crypto_rating_daily: 3743 rows, 21 cols, 3 indexes
-- vitality_scores: 15144 rows, 15 cols, 1 indexes
-- defi_yields: 18784 rows, 11 cols, 1 indexes