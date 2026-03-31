#!/usr/bin/env python3
"""NERQ CRYPTO — Sprint 1, Uppgift 1.1 — v2 (yearly chunks)"""

import sqlite3, requests, time, logging, argparse, os, sys
from datetime import datetime, timezone

DB_PATH = "crypto_trust.db"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
RATE_LIMIT_DELAY = 2.5
MAX_RETRIES = 5
RETRY_BASE_DELAY = 15

YEAR_CHUNKS = [
    (int(datetime(2021,1,1,tzinfo=timezone.utc).timestamp()), int(datetime(2021,12,31,tzinfo=timezone.utc).timestamp()), "2021"),
    (int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp()), int(datetime(2022,12,31,tzinfo=timezone.utc).timestamp()), "2022"),
    (int(datetime(2023,1,1,tzinfo=timezone.utc).timestamp()), int(datetime(2023,12,31,tzinfo=timezone.utc).timestamp()), "2023"),
    (int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp()), int(datetime(2024,12,31,tzinfo=timezone.utc).timestamp()), "2024"),
    (int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp()), int(datetime.now(timezone.utc).timestamp()), "2025"),
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
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
            if r.status_code in (429, 401):
                wait = RETRY_BASE_DELAY * (2 ** attempt)
                log.warning(f"  {r.status_code} — väntar {wait}s (försök {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            log.error(f"  API {r.status_code}: {r.text[:150]}")
            return None
        except Exception as e:
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    return None

def fetch_top_tokens(n=300):
    tokens = []
    for page in range(1, (n // 250) + 2):
        need = min(250, n - len(tokens))
        if need <= 0:
            break
        log.info(f"Hämtar token-lista sida {page} ({need} st)...")
        data = api_get(f"{COINGECKO_BASE}/coins/markets", {
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": need, "page": page, "sparkline": "false"
        })
        if not data:
            break
        tokens.extend(data)
        time.sleep(RATE_LIMIT_DELAY)
    log.info(f"Totalt {len(tokens)} tokens hämtade")
    return tokens[:n]

def fetch_and_save_token(conn, token_id, name, rank, idx, total):
    log.info(f"[{idx}/{total}] {name} ({token_id}) rank #{rank}")
    all_rows = []
    prev_close = None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    for from_ts, to_ts, label in YEAR_CHUNKS:
        time.sleep(RATE_LIMIT_DELAY)
        data = api_get(f"{COINGECKO_BASE}/coins/{token_id}/market_chart/range", {
            "vs_currency": "usd", "from": from_ts, "to": to_ts
        })
        if not data or "prices" not in data or not data["prices"]:
            log.info(f"  {label}: ingen data")
            continue

        prices = data["prices"]
        mcaps = {int(m[0]): m[1] for m in data.get("market_caps", []) if m[1]}
        vols = {int(v[0]): v[1] for v in data.get("total_volumes", []) if v[1]}

        count = 0
        for ts_ms, close in prices:
            if close is None:
                continue
            ts_int = int(ts_ms)
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
            op = prev_close if prev_close else close
            all_rows.append({
                "token_id": token_id, "date": date_str,
                "open": round(op, 8), "high": round(max(op, close), 8),
                "low": round(min(op, close), 8), "close": round(close, 8),
                "volume": round(vols.get(ts_int, 0), 2) or None,
                "market_cap": round(mcaps.get(ts_int, 0), 2) or None,
                "fetched_at": now,
            })
            prev_close = close
            count += 1
        log.info(f"  {label}: {count} dagar")

    if not all_rows:
        conn.execute("UPDATE crypto_fetch_status SET status='error', error_message='No data' WHERE token_id=?", (token_id,))
        conn.commit()
        return False

    # Dedup
    seen = set()
    unique = []
    for r in all_rows:
        k = r["date"]
        if k not in seen:
            seen.add(k)
            unique.append(r)

    conn.executemany("""INSERT OR REPLACE INTO crypto_price_history
        (token_id, date, open, high, low, close, volume, market_cap, fetched_at)
        VALUES (:token_id,:date,:open,:high,:low,:close,:volume,:market_cap,:fetched_at)""", unique)

    dates = [r["date"] for r in unique]
    conn.execute("""UPDATE crypto_fetch_status SET status='completed', rows_fetched=?,
        first_date=?, last_date=? WHERE token_id=?""",
        (len(unique), min(dates), max(dates), token_id))
    conn.commit()
    log.info(f"  ✓ {len(unique)} dagar ({min(dates)} → {max(dates)})")
    return True

def main():
    parser = argparse.ArgumentParser()
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
        log.info(f"Tokens klara: {c} | Fel: {e} | Rader: {r:,} | Spann: {dr[0]} → {dr[1]}")
        return

    # Populate token list
    existing = conn.execute("SELECT COUNT(*) FROM crypto_fetch_status").fetchone()[0]
    if existing < args.top:
        tokens = fetch_top_tokens(args.top)
        for t in tokens:
            conn.execute("INSERT OR IGNORE INTO crypto_fetch_status (token_id,name,symbol,market_cap_rank,status) VALUES (?,?,?,?,'pending')",
                (t["id"], t.get("name",""), t.get("symbol","").upper(), t.get("market_cap_rank",9999)))
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM crypto_fetch_status").fetchone()[0]
        log.info(f"Token-lista: {total} tokens")

    if args.force and args.token:
        conn.execute("UPDATE crypto_fetch_status SET status='pending' WHERE token_id=?", (args.token,))
        conn.commit()

    pending = conn.execute("SELECT token_id, name, symbol, market_cap_rank FROM crypto_fetch_status WHERE status != 'completed' ORDER BY market_cap_rank").fetchall()
    completed = conn.execute("SELECT COUNT(*) FROM crypto_fetch_status WHERE status='completed'").fetchone()[0]
    total = completed + len(pending)

    if not pending:
        log.info("Alla tokens klara!")
        return

    est = len(pending) * 14 / 60
    log.info(f"Kvar: {len(pending)} tokens (~{est:.0f} min)")
    log.info("=" * 50)

    ok = err = 0
    t0 = time.time()
    for i, (tid, name, sym, rank) in enumerate(pending, 1):
        try:
            if fetch_and_save_token(conn, tid, name or tid, rank or 0, completed+i, total):
                ok += 1
            else:
                err += 1
        except KeyboardInterrupt:
            log.info("\n⏸ Avbrutet. Kör igen för att fortsätta.")
            break
        except Exception as e:
            log.error(f"  ✗ {e}")
            conn.execute("UPDATE crypto_fetch_status SET status='error', error_message=? WHERE token_id=?", (str(e)[:300], tid))
            conn.commit()
            err += 1
        if i % 10 == 0:
            el = time.time() - t0
            rem = (len(pending)-i) * (el/i) / 60
            rows = conn.execute("SELECT COUNT(*) FROM crypto_price_history").fetchone()[0]
            log.info(f"--- {completed+i}/{total} | {ok} ok {err} fel | {rows:,} rader | ~{rem:.0f} min kvar ---")

    el = time.time() - t0
    rows = conn.execute("SELECT COUNT(*) FROM crypto_price_history").fetchone()[0]
    log.info(f"KLART: {ok} ok, {err} fel, {el/60:.1f} min, {rows:,} rader totalt")
    conn.close()

if __name__ == "__main__":
    main()
