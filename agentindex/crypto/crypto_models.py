"""
Nerq Crypto Module — Database Models
SQLite schema for crypto tokens, exchanges, DeFi protocols.
Compatible with existing Trust Score v2.2 pattern.
"""

import sqlite3
from pathlib import Path
from crypto_config import CRYPTO_DB_PATH


def get_db():
    """Get database connection with WAL mode for concurrent access."""
    Path(CRYPTO_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CRYPTO_DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all crypto tables if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()

    # ── Tokens/Coins ──────────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crypto_tokens (
        id TEXT PRIMARY KEY,                    -- coingecko id e.g. 'bitcoin'
        symbol TEXT NOT NULL,                   -- e.g. 'btc'
        name TEXT NOT NULL,                     -- e.g. 'Bitcoin'
        
        -- Market data
        current_price_usd REAL,
        market_cap_usd REAL,
        market_cap_rank INTEGER,
        total_volume_24h_usd REAL,
        price_change_24h_pct REAL,
        price_change_7d_pct REAL,
        price_change_30d_pct REAL,
        
        -- Supply
        circulating_supply REAL,
        total_supply REAL,
        max_supply REAL,
        
        -- Trust signals
        ath_usd REAL,
        ath_date TEXT,
        atl_usd REAL,
        atl_date TEXT,
        fully_diluted_valuation REAL,
        
        -- Metadata from detail endpoint
        categories TEXT,                        -- JSON array
        platforms TEXT,                          -- JSON dict {chain: contract_address}
        contract_address TEXT,                   -- primary contract address
        homepage TEXT,
        github_repos TEXT,                       -- JSON array of repo URLs
        twitter_handle TEXT,
        telegram_url TEXT,
        subreddit_url TEXT,
        
        -- Security signals (from detail endpoint)
        has_audit INTEGER DEFAULT 0,            -- known audit exists
        is_verified INTEGER DEFAULT 0,          -- CoinGecko verified
        
        -- Community metrics
        twitter_followers INTEGER,
        reddit_subscribers INTEGER,
        github_stars INTEGER,
        github_forks INTEGER,
        github_total_issues INTEGER,
        github_closed_issues INTEGER,
        github_contributors INTEGER,
        github_last_commit TEXT,                -- ISO date
        
        -- Scores (calculated later by crypto_trust_score.py)
        trust_score REAL,
        trust_grade TEXT,
        security_score REAL,
        compliance_score REAL,
        maintenance_score REAL,
        popularity_score REAL,
        ecosystem_score REAL,
        
        -- Metadata
        crawled_at TEXT NOT NULL,               -- ISO datetime
        detail_crawled_at TEXT,                 -- when /coins/{id} was fetched
        scored_at TEXT,
        source TEXT DEFAULT 'coingecko'
    )
    """)

    # ── Exchanges ─────────────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crypto_exchanges (
        id TEXT PRIMARY KEY,                    -- coingecko id e.g. 'binance'
        name TEXT NOT NULL,
        
        -- Volume & ranking
        trust_score_cg INTEGER,                 -- CoinGecko's own trust score (1-10)
        trust_score_rank INTEGER,
        trade_volume_24h_btc REAL,
        trade_volume_24h_usd REAL,
        
        -- Metadata
        year_established INTEGER,
        country TEXT,
        url TEXT,
        has_trading_incentive INTEGER,
        
        -- Trust signals
        proof_of_reserves INTEGER DEFAULT 0,
        hack_history TEXT,                      -- JSON array of incidents
        regulatory_status TEXT,                 -- JSON dict {jurisdiction: status}
        
        -- Scores
        trust_score REAL,
        trust_grade TEXT,
        security_score REAL,
        compliance_score REAL,
        maintenance_score REAL,
        popularity_score REAL,
        ecosystem_score REAL,
        
        -- Metadata
        crawled_at TEXT NOT NULL,
        scored_at TEXT,
        source TEXT DEFAULT 'coingecko'
    )
    """)

    # ── DeFi Protocols ────────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crypto_defi_protocols (
        id TEXT PRIMARY KEY,                    -- defillama slug e.g. 'aave'
        name TEXT NOT NULL,
        
        -- TVL data
        tvl_usd REAL,
        tvl_change_1d REAL,
        tvl_change_7d REAL,
        tvl_change_30d REAL,
        
        -- Metadata
        category TEXT,                          -- e.g. 'Lending', 'DEX', 'Bridge'
        chains TEXT,                            -- JSON array of chains
        url TEXT,
        twitter TEXT,
        github TEXT,
        
        -- Trust signals
        audit_status TEXT,                      -- JSON array of audit firms
        hack_history TEXT,                      -- JSON array of incidents
        
        -- Scores
        trust_score REAL,
        trust_grade TEXT,
        security_score REAL,
        compliance_score REAL,
        maintenance_score REAL,
        popularity_score REAL,
        ecosystem_score REAL,
        
        -- Metadata
        crawled_at TEXT NOT NULL,
        scored_at TEXT,
        source TEXT DEFAULT 'defillama'
    )
    """)

    # ── Trust Score History (for all crypto entities) ─────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crypto_trust_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,              -- 'token', 'exchange', 'defi'
        trust_score REAL,
        trust_grade TEXT,
        snapshot_date TEXT NOT NULL,
        UNIQUE(entity_id, entity_type, snapshot_date)
    )
    """)

    # ── Indexes ───────────────────────────────────────────────────
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_symbol ON crypto_tokens(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_market_cap_rank ON crypto_tokens(market_cap_rank)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_trust_score ON crypto_tokens(trust_score)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_trust_grade ON crypto_tokens(trust_grade)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exchanges_trust ON crypto_exchanges(trust_score)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_defi_tvl ON crypto_defi_protocols(tvl_usd)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_entity ON crypto_trust_history(entity_id, entity_type)")

    conn.commit()
    conn.close()
    print(f"✅ Crypto DB initialized at {CRYPTO_DB_PATH}")


if __name__ == "__main__":
    init_db()
