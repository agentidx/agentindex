"""
Nerq Crypto Module — CoinGecko Crawler
Punkt 25: Crawla alla 13K+ tokens med pris, volym, market cap etc.

Usage:
    python crypto_crawler.py                    # Full crawl: tokens + exchanges
    python crypto_crawler.py --tokens-only      # Only tokens
    python crypto_crawler.py --exchanges-only   # Only exchanges
    python crypto_crawler.py --details          # Also fetch /coins/{id} for top 500

Rate limit: 30 calls/min (Demo plan). We use 2.1s delay = ~28 calls/min.
"""

import argparse
import json
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ requests not installed. Run: pip install requests --break-system-packages")
    sys.exit(1)

from crypto_config import (
    COINGECKO_API_KEY, COINGECKO_BASE_URL,
    CRAWL_BATCH_SIZE, CRAWL_DELAY_SECONDS, CRAWL_MAX_PAGES
)
from crypto_models import get_db, init_db


# ── HTTP Session ──────────────────────────────────────────────────

def _n(val):
    """Safely convert numeric values — huge ints (meme coin supplies) overflow SQLite INTEGER."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError, OverflowError):
        return None

def make_session():
    """Create requests session with CoinGecko API key header."""
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "User-Agent": "Nerq/1.0 (https://nerq.ai) CryptoCrawler"
    })
    if COINGECKO_API_KEY:
        # Demo API key uses x-cg-demo-api-key header
        s.headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
    return s


def api_get(session, endpoint, params=None, retries=3):
    """GET request with rate-limit handling and retries."""
    url = f"{COINGECKO_BASE_URL}{endpoint}"
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=30)
            
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                print(f"  ⏳ Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            else:
                print(f"  ⚠️ HTTP {resp.status_code} for {endpoint} (attempt {attempt+1})")
                time.sleep(5)
                continue
                
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️ Request error: {e} (attempt {attempt+1})")
            time.sleep(5)
            continue
    
    print(f"  ❌ Failed after {retries} attempts: {endpoint}")
    return None


# ── Token Crawler ─────────────────────────────────────────────────

def crawl_tokens(session):
    """
    Crawl all tokens via /coins/markets endpoint.
    Returns count of tokens crawled.
    """
    print("\n🪙  CRAWLING TOKENS via /coins/markets")
    print(f"   Batch size: {CRAWL_BATCH_SIZE}, Max pages: {CRAWL_MAX_PAGES}")
    print(f"   Delay: {CRAWL_DELAY_SECONDS}s between calls\n")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    total = 0
    
    for page in range(1, CRAWL_MAX_PAGES + 1):
        data = api_get(session, "/coins/markets", params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": CRAWL_BATCH_SIZE,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "7d,30d",
            "locale": "en"
        })
        
        if not data or len(data) == 0:
            print(f"   Page {page}: empty response — done!")
            break
        
        for coin in data:
            conn.execute("""
                INSERT INTO crypto_tokens (
                    id, symbol, name,
                    current_price_usd, market_cap_usd, market_cap_rank,
                    total_volume_24h_usd, price_change_24h_pct,
                    price_change_7d_pct, price_change_30d_pct,
                    circulating_supply, total_supply, max_supply,
                    ath_usd, ath_date, atl_usd, atl_date,
                    fully_diluted_valuation,
                    crawled_at
                ) VALUES (
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?,
                    ?
                )
                ON CONFLICT(id) DO UPDATE SET
                    current_price_usd = excluded.current_price_usd,
                    market_cap_usd = excluded.market_cap_usd,
                    market_cap_rank = excluded.market_cap_rank,
                    total_volume_24h_usd = excluded.total_volume_24h_usd,
                    price_change_24h_pct = excluded.price_change_24h_pct,
                    price_change_7d_pct = excluded.price_change_7d_pct,
                    price_change_30d_pct = excluded.price_change_30d_pct,
                    circulating_supply = excluded.circulating_supply,
                    total_supply = excluded.total_supply,
                    max_supply = excluded.max_supply,
                    ath_usd = excluded.ath_usd,
                    ath_date = excluded.ath_date,
                    atl_usd = excluded.atl_usd,
                    atl_date = excluded.atl_date,
                    fully_diluted_valuation = excluded.fully_diluted_valuation,
                    crawled_at = excluded.crawled_at
            """, (
                coin.get("id"), coin.get("symbol", "").lower(), coin.get("name", ""),
                _n(coin.get("current_price")), _n(coin.get("market_cap")), coin.get("market_cap_rank"),
                _n(coin.get("total_volume")), _n(coin.get("price_change_percentage_24h")),
                _n(coin.get("price_change_percentage_7d_in_currency")),
                _n(coin.get("price_change_percentage_30d_in_currency")),
                _n(coin.get("circulating_supply")), _n(coin.get("total_supply")), _n(coin.get("max_supply")),
                _n(coin.get("ath")), coin.get("ath_date"), _n(coin.get("atl")), coin.get("atl_date"),
                _n(coin.get("fully_diluted_valuation")),
                now
            ))
        
        total += len(data)
        print(f"   Page {page}: +{len(data)} tokens (total: {total})")
        
        if page % 10 == 0:
            conn.commit()
            print(f"   💾 Committed {total} tokens to DB")
        
        time.sleep(CRAWL_DELAY_SECONDS)
    
    conn.commit()
    conn.close()
    print(f"\n✅ Token crawl complete: {total} tokens saved")
    return total


# ── Token Detail Crawler ──────────────────────────────────────────

def crawl_token_details(session, limit=500):
    """
    Fetch detailed info for top N tokens via /coins/{id}.
    This gives us: categories, platforms, contract addresses, 
    github repos, community metrics, developer data.
    
    SLOW: 1 call per token, 2.1s delay = ~17 min for 500 tokens.
    """
    print(f"\n🔍 CRAWLING TOKEN DETAILS (top {limit})")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    # Get top tokens that haven't been detail-crawled yet (or crawled >24h ago)
    rows = conn.execute("""
        SELECT id FROM crypto_tokens 
        WHERE detail_crawled_at IS NULL 
           OR detail_crawled_at < datetime('now', '-24 hours')
        ORDER BY market_cap_rank ASC NULLS LAST
        LIMIT ?
    """, (limit,)).fetchall()
    
    print(f"   {len(rows)} tokens need detail crawl\n")
    
    for i, row in enumerate(rows):
        token_id = row["id"]
        data = api_get(session, f"/coins/{token_id}", params={
            "localization": "false",
            "tickers": "false",
            "market_data": "false",  # already have from /markets
            "community_data": "true",
            "developer_data": "true",
            "sparkline": "false"
        })
        
        if not data:
            continue
        
        # Extract nested data safely
        links = data.get("links", {})
        dev = data.get("developer_data", {})
        community = data.get("community_data", {})
        repos = links.get("repos_url", {}).get("github", [])
        
        conn.execute("""
            UPDATE crypto_tokens SET
                categories = ?,
                platforms = ?,
                contract_address = ?,
                homepage = ?,
                github_repos = ?,
                twitter_handle = ?,
                telegram_url = ?,
                subreddit_url = ?,
                twitter_followers = ?,
                reddit_subscribers = ?,
                github_stars = ?,
                github_forks = ?,
                github_total_issues = ?,
                github_closed_issues = ?,
                github_contributors = ?,
                github_last_commit = ?,
                detail_crawled_at = ?
            WHERE id = ?
        """, (
            json.dumps(data.get("categories", [])),
            json.dumps(data.get("platforms", {})),
            (data.get("platforms", {}) or {}).get("ethereum") 
                or (data.get("platforms", {}) or {}).get("binance-smart-chain")
                or data.get("contract_address"),
            (links.get("homepage", [None]) or [None])[0],
            json.dumps(repos),
            links.get("twitter_screen_name"),
            (links.get("telegram_channel_identifier") or ""),
            (links.get("subreddit_url") or ""),
            community.get("twitter_followers"),
            community.get("reddit_subscribers"),
            dev.get("stars"),
            dev.get("forks"),
            dev.get("total_issues"),
            dev.get("closed_issues"),
            dev.get("pull_request_contributors"),
            (dev.get("last_4_weeks_commit_activity_series") or [None])[-1] if dev.get("last_4_weeks_commit_activity_series") else None,
            now,
            token_id
        ))
        
        print(f"   [{i+1}/{len(rows)}] {token_id} — categories: {len(data.get('categories', []))}, repos: {len(repos)}")
        
        if (i + 1) % 25 == 0:
            conn.commit()
        
        time.sleep(CRAWL_DELAY_SECONDS)
    
    conn.commit()
    conn.close()
    print(f"\n✅ Token details complete: {len(rows)} tokens enriched")
    return len(rows)


# ── Exchange Crawler ──────────────────────────────────────────────

def crawl_exchanges(session):
    """
    Crawl all exchanges via /exchanges endpoint.
    CoinGecko lists ~600+ exchanges with trust scores.
    """
    print("\n🏦 CRAWLING EXCHANGES via /exchanges")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    total = 0
    
    for page in range(1, 10):  # Max ~800 exchanges
        data = api_get(session, "/exchanges", params={
            "per_page": 250,
            "page": page
        })
        
        if not data or len(data) == 0:
            break
        
        for ex in data:
            conn.execute("""
                INSERT INTO crypto_exchanges (
                    id, name, trust_score_cg, trust_score_rank,
                    trade_volume_24h_btc, country, url, 
                    year_established, has_trading_incentive,
                    crawled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    trust_score_cg = excluded.trust_score_cg,
                    trust_score_rank = excluded.trust_score_rank,
                    trade_volume_24h_btc = excluded.trade_volume_24h_btc,
                    country = excluded.country,
                    url = excluded.url,
                    year_established = excluded.year_established,
                    has_trading_incentive = excluded.has_trading_incentive,
                    crawled_at = excluded.crawled_at
            """, (
                ex.get("id"), ex.get("name"),
                ex.get("trust_score"), ex.get("trust_score_rank"),
                ex.get("trade_volume_24h_btc"),
                ex.get("country"), ex.get("url"),
                ex.get("year_established"),
                1 if ex.get("has_trading_incentive") else 0,
                now
            ))
        
        total += len(data)
        print(f"   Page {page}: +{len(data)} exchanges (total: {total})")
        conn.commit()
        time.sleep(CRAWL_DELAY_SECONDS)
    
    conn.close()
    print(f"\n✅ Exchange crawl complete: {total} exchanges saved")
    return total


# ── Stats ─────────────────────────────────────────────────────────

def print_stats():
    """Print current database stats."""
    conn = get_db()
    
    tokens = conn.execute("SELECT COUNT(*) as c FROM crypto_tokens").fetchone()["c"]
    tokens_detailed = conn.execute("SELECT COUNT(*) as c FROM crypto_tokens WHERE detail_crawled_at IS NOT NULL").fetchone()["c"]
    tokens_scored = conn.execute("SELECT COUNT(*) as c FROM crypto_tokens WHERE trust_score IS NOT NULL").fetchone()["c"]
    exchanges = conn.execute("SELECT COUNT(*) as c FROM crypto_exchanges").fetchone()["c"]
    
    top_token = conn.execute("SELECT name, market_cap_usd FROM crypto_tokens ORDER BY market_cap_rank ASC LIMIT 1").fetchone()
    
    print("\n📊 CRYPTO DATABASE STATS")
    print(f"   Tokens:     {tokens:,} ({tokens_detailed:,} with details, {tokens_scored:,} scored)")
    print(f"   Exchanges:  {exchanges:,}")
    if top_token:
        mcap = top_token["market_cap_usd"]
        print(f"   Top token:  {top_token['name']} (${mcap:,.0f} market cap)" if mcap else f"   Top token:  {top_token['name']}")
    print(f"   DB path:    {CRYPTO_DB_PATH}")
    
    conn.close()


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nerq Crypto Crawler — CoinGecko")
    parser.add_argument("--tokens-only", action="store_true", help="Only crawl tokens")
    parser.add_argument("--exchanges-only", action="store_true", help="Only crawl exchanges")
    parser.add_argument("--details", action="store_true", help="Also fetch token details (slow)")
    parser.add_argument("--detail-limit", type=int, default=500, help="Number of tokens to detail-crawl (default: 500)")
    parser.add_argument("--stats", action="store_true", help="Print DB stats and exit")
    args = parser.parse_args()
    
    # Check API key
    if not COINGECKO_API_KEY:
        print("❌ COINGECKO_API_KEY not set!")
        print("   Option 1: export COINGECKO_API_KEY='your-key-here'")
        print("   Option 2: Create crypto/.env file with COINGECKO_API_KEY=your-key-here")
        sys.exit(1)
    
    print("=" * 60)
    print("  NERQ CRYPTO CRAWLER — CoinGecko")
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print(f"  API Key: {COINGECKO_API_KEY[:8]}...{COINGECKO_API_KEY[-4:]}")
    print("=" * 60)
    
    # Init database
    init_db()
    
    if args.stats:
        print_stats()
        return
    
    session = make_session()
    
    # Verify API key works
    ping = api_get(session, "/ping")
    if not ping:
        print("❌ CoinGecko API unreachable or key invalid")
        sys.exit(1)
    print(f"✅ CoinGecko API connected: {ping}")
    
    start = time.time()
    
    if not args.exchanges_only:
        crawl_tokens(session)
    
    if not args.tokens_only:
        crawl_exchanges(session)
    
    if args.details:
        crawl_token_details(session, limit=args.detail_limit)
    
    elapsed = time.time() - start
    print(f"\n⏱️  Total time: {elapsed/60:.1f} minutes")
    
    print_stats()


if __name__ == "__main__":
    main()
