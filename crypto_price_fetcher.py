#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 1, Uppgift 1.1 — v3
Använder CryptoCompare (gratis, full historik) + CoinGecko (token-lista).

CryptoCompare histoday: 2000 dagar per anrop, inga begränsningar bakåt.
Vi hämtar 2000 dagar (2019→2025) i ETT anrop per token.
"""

import sqlite3, requests, time, logging, argparse, os, sys, json
from datetime import datetime, timezone

DB_PATH = "crypto_trust.db"
CG_BASE = "https://api.coingecko.com/api/v3"
CC_BASE = "https://min-api.cryptocompare.com/data/v2"
RATE_LIMIT_DELAY = 1.5  # CryptoCompare är generösare
MAX_RETRIES = 4
RETRY_BASE_DELAY = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("crypto_price_fetcher.log", encoding="utf-8")
    ]
)
log = logging.getLogger("nerq")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS crypto_price_history (
        token_id TEXT NOT NULL, date TEXT NOT NULL, open REAL, high REAL, low REAL,
        close REAL, volume REAL, market_cap REAL, fetched_at TEXT NOT NULL,
        PRIMARY KEY (token_id, date))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_td ON crypto_price_history(token_id, date)")
    conn.execute("""CREATE TABLE IF NOT EXISTS crypto_fetch_status (
        token_id TEXT PRIMARY KEY, name TEXT, symbol TEXT, market_cap_rank INTEGER,
        status TEXT DEFAULT 'pending', rows_fetched INTEGER DEFAULT 0,
        first_date TEXT, last_date TEXT, error_message TEXT)""")
    conn.commit()
    return conn

def api_get(url, params=None):
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = RETRY_BASE_DELAY * (2 ** attempt)
                log.warning(f"  429 — väntar {wait}s (försök {attempt+1})")
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            log.error(f"  HTTP {r.status_code}: {r.text[:150]}")
            return None
        except Exception:
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    return None

def fetch_top_tokens(n=300):
    """Hämta topp N tokens från CoinGecko (symbol + metadata)."""
    tokens = []
    for page in range(1, (n // 250) + 2):
        need = min(250, n - len(tokens))
        if need <= 0:
            break
        log.info(f"CoinGecko: hämtar token-lista sida {page}...")
        data = api_get(f"{CG_BASE}/coins/markets", {
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": need, "page": page, "sparkline": "false"
        })
        if not data:
            break
        tokens.extend(data)
        time.sleep(2.5)
    log.info(f"Hämtade {len(tokens)} tokens")
    return tokens[:n]

def fetch_cc_daily(symbol, limit=2000):
    """
    Hämta daglig OHLCV från CryptoCompare.
    histoday med limit=2000 ger ~5.5 år bakåt (gratis, ingen begränsning).
    """
    data = api_get(f"{CC_BASE}/histoday", {
        "fsym": symbol,
        "tsym": "USD",
        "limit": limit,
        "allData": "false"
    })
    if not data:
        return None
    if data.get("Response") == "Error":
        return None
    return data.get("Data", {}).get("Data", [])

def fetch_and_save_token(conn, token_id, name, symbol, rank, idx, total):
    log.info(f"[{idx}/{total}] {name} ({symbol}) rank #{rank}")

    time.sleep(RATE_LIMIT_DELAY)
    bars = fetch_cc_daily(symbol, limit=2000)

    if not bars:
        log.warning(f"  ⚠ Ingen data från CryptoCompare för {symbol}")
        conn.execute("UPDATE crypto_fetch_status SET status='error', error_message='No CryptoCompare data' WHERE token_id=?", (token_id,))
        conn.commit()
        return False

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = []

    for bar in bars:
        ts = bar.get("time", 0)
        if ts == 0:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        # Filtrera: bara 2021-01-01 och framåt
        if dt.year < 2021:
            continue
        # Hoppa noll-rader (token ej lanserad)
        if bar.get("close", 0) == 0 and bar.get("open", 0) == 0:
            continue

        rows.append({
            "token_id": token_id,
            "date": dt.strftime("%Y-%m-%d"),
            "open": bar.get("open"),
            "high": bar.get("high"),
            "low": bar.get("low"),
            "close": bar.get("close"),
            "volume": bar.get("volumeto"),   # volumeto = USD volume
            "market_cap": None,               # CryptoCompare ger ej mcap i histoday
            "fetched_at": now,
        })

    if not rows:
        log.info(f"  Inga rader efter 2021-01-01")
        conn.execute("UPDATE crypto_fetch_status SET status='completed', rows_fetched=0 WHERE token_id=?", (token_id,))
        conn.commit()
        return True

    # Dedup
    seen = set()
    unique = []
    for r in rows:
        if r["date"] not in seen:
            seen.add(r["date"])
            unique.append(r)

    conn.executemany("""INSERT OR REPLACE INTO crypto_price_history
        (token_id, date, open, high, low, close, volume, market_cap, fetched_at)
        VALUES (:token_id,:date,:open,:high,:low,:close,:volume,:market_cap,:fetched_at)""", unique)

    dates = [r["date"] for r in unique]
    conn.execute("""UPDATE crypto_fetch_status SET status='completed', rows_fetched=?,
        first_date=?, last_date=? WHERE token_id=?""",
        (len(unique), min(dates), max(dates), token_id))
    conn.commit()
    log.info(f"  ✓ {len(unique)} dagar OHLCV ({min(dates)} → {max(dates)})")
    return True

def main():
    parser = argparse.ArgumentParser(description="NERQ Crypto Prishistorik v3 (CryptoCompare)")
    parser.add_argument("--top", type=int, default=300)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--token", type=str)
    args = parser.parse_args()

    conn = init_db()

    if args.status:
        c = conn.execute("SELECT COUNT(*) FROM crypto_fetch_status WHERE status='completed'").fetchone()[0]
        r = conn.execute("SELECT COUNT(*) FROM crypto_price_history").fetchone()[0]
        e = conn.execute("SELECT COUNT(*) FROM crypto_fetch_status WHERE status='error'").fetchone()[0]
        dr = conn.execute("SELECT MIN(date), MAX(date) FROM crypto_price_history").fetchone()
        sz = os.path.getsize(DB_PATH) / 1024 / 1024 if os.path.exists(DB_PATH) else 0
        log.info(f"Klara: {c} | Fel: {e} | Rader: {r:,} | Spann: {dr[0] or '?'} → {dr[1] or '?'} | DB: {sz:.1f}MB")
        return

    # Hämta token-lista från CoinGecko
    existing = conn.execute("SELECT COUNT(*) FROM crypto_fetch_status").fetchone()[0]
    if existing < args.top:
        tokens = fetch_top_tokens(args.top)
        for t in tokens:
            conn.execute("""INSERT OR IGNORE INTO crypto_fetch_status
                (token_id, name, symbol, market_cap_rank, status)
                VALUES (?,?,?,?,'pending')""",
                (t["id"], t.get("name",""), t.get("symbol","").upper(), t.get("market_cap_rank",9999)))
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM crypto_fetch_status").fetchone()[0]
        log.info(f"Token-lista: {total} tokens")

    if args.force and args.token:
        conn.execute("UPDATE crypto_fetch_status SET status='pending' WHERE token_id=?", (args.token,))
        conn.commit()

    pending = conn.execute("""SELECT token_id, name, symbol, market_cap_rank
        FROM crypto_fetch_status WHERE status != 'completed'
        ORDER BY market_cap_rank""").fetchall()
    completed = conn.execute("SELECT COUNT(*) FROM crypto_fetch_status WHERE status='completed'").fetchone()[0]
    total = completed + len(pending)

    if not pending:
        log.info("Alla tokens klara!")
        conn.close()
        return

    # CryptoCompare: 1 anrop per token, ~1.5s delay = ~8 min för 300 tokens
    est = len(pending) * 2 / 60
    log.info(f"Kvar: {len(pending)} tokens (~{est:.0f} min)")
    log.info(f"Källa: CryptoCompare histoday (2000 dagar, gratis, full OHLCV)")
    log.info("=" * 50)

    ok = err = 0
    t0 = time.time()

    for i, (tid, name, sym, rank) in enumerate(pending, 1):
        try:
            if fetch_and_save_token(conn, tid, name or tid, sym or "?", rank or 0, completed+i, total):
                ok += 1
            else:
                err += 1
        except KeyboardInterrupt:
            log.info("\n⏸ Avbrutet. Kör igen för att fortsätta.")
            break
        except Exception as e:
            log.error(f"  ✗ {e}")
            conn.execute("UPDATE crypto_fetch_status SET status='error', error_message=? WHERE token_id=?",
                (str(e)[:300], tid))
            conn.commit()
            err += 1

        if i % 25 == 0:
            el = time.time() - t0
            rem = (len(pending)-i) * (el/i) / 60
            rows = conn.execute("SELECT COUNT(*) FROM crypto_price_history").fetchone()[0]
            log.info(f"--- {completed+i}/{total} | {ok} ok {err} fel | {rows:,} rader | ~{rem:.0f} min kvar ---")

    el = time.time() - t0
    rows = conn.execute("SELECT COUNT(*) FROM crypto_price_history").fetchone()[0]
    log.info("=" * 50)
    log.info(f"KLART: {ok} ok, {err} fel, {el/60:.1f} min, {rows:,} rader")

    # Visa sammanfattning
    dr = conn.execute("SELECT MIN(date), MAX(date) FROM crypto_price_history").fetchone()
    sz = os.path.getsize(DB_PATH) / 1024 / 1024
    log.info(f"Spann: {dr[0]} → {dr[1]} | DB: {sz:.1f}MB")
    conn.close()

if __name__ == "__main__":
    main()
