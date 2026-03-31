"""
Sprint 9 Extension: Yield History Crawler
Hämtar historisk APY + TVL per pool från DeFiLlama (gratis endpoint).

Endpoint: https://yields.llama.fi/chart/{pool_id}
Returnerar dagliga datapunkter sedan poolens start (typiskt 2022-2026).

Kör: python3 yield_history_crawler.py
Tar ~20-30 min för alla 6,539 pooler (5 req/sek rate limit).

Tabell: defi_yield_history
  pool_id, date, tvl_usd, apy, apy_base, apy_reward, il_7d, apy_base_7d
"""

import sqlite3
import requests
import time
import json
from datetime import datetime, timezone
from typing import Optional

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
BASE_URL = "https://yields.llama.fi/chart"
RATE_LIMIT = 1.0        # sekunder mellan requests (5 req/sek)
BATCH_COMMIT = 100      # commit var 100:e pool
LOOKBACK_DAYS = 90      # spara max 90 dagars historik per pool (räcker för alla signaler)


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS defi_yield_history (
            pool_id     TEXT NOT NULL,
            date        TEXT NOT NULL,
            tvl_usd     REAL,
            apy         REAL,
            apy_base    REAL,
            apy_reward  REAL,
            il_7d       REAL,
            apy_base_7d REAL,
            PRIMARY KEY (pool_id, date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dyh_pool ON defi_yield_history(pool_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dyh_date ON defi_yield_history(date DESC)")
    conn.commit()
    print("✅ Tabell defi_yield_history redo")


def get_all_pools(conn) -> list:
    """Hämta alla pool_ids från defi_yields."""
    rows = conn.execute("SELECT pool_id, project, chain, symbol FROM defi_yields ORDER BY tvl_usd DESC NULLS LAST").fetchall()
    return rows


def get_already_crawled(conn) -> set:
    """Pooler som redan har historik."""
    rows = conn.execute("SELECT DISTINCT pool_id FROM defi_yield_history").fetchall()
    return {r[0] for r in rows}


def fetch_pool_history(pool_id: str) -> Optional[list]:
    """
    Hämta historik för en pool från DeFiLlama.
    Returnerar lista av dicts eller None vid fel.
    """
    try:
        resp = requests.get(f"{BASE_URL}/{pool_id}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", [])
        elif resp.status_code == 429:
            for wait in [10, 20, 30]:
                time.sleep(wait)
                try:
                    resp2 = requests.get(f"{BASE_URL}/{pool_id}", timeout=10)
                    if resp2.status_code == 200:
                        return resp2.json().get("data", [])
                except Exception:
                    pass
            return None
        else:
            return None
    except Exception as e:
        return None


def save_history(conn, pool_id: str, history: list, lookback_days: int = LOOKBACK_DAYS):
    """Spara historik för en pool. Begränsar till senaste N dagar."""
    if not history:
        return 0

    # Filtrera till senaste N dagar
    cutoff = None
    if lookback_days:
        from datetime import timedelta
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        cutoff = cutoff_dt.strftime("%Y-%m-%d")

    rows = []
    for point in history:
        ts = point.get("timestamp", "")
        date = ts[:10] if ts else None  # "2024-01-15"
        if not date:
            continue
        if cutoff and date < cutoff:
            continue

        rows.append((
            pool_id,
            date,
            point.get("tvlUsd"),
            point.get("apy"),
            point.get("apyBase"),
            point.get("apyReward"),
            point.get("il7d"),
            point.get("apyBase7d"),
        ))

    if rows:
        conn.executemany("""
            INSERT OR REPLACE INTO defi_yield_history
            (pool_id, date, tvl_usd, apy, apy_base, apy_reward, il_7d, apy_base_7d)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)

    return len(rows)


def run_crawler(resume: bool = True, max_pools: Optional[int] = None):
    """
    Huvudfunktion. resume=True hoppar över redan crawlade pooler.
    max_pools=None kör alla, annars begränsar.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    init_db(conn)

    pools = get_all_pools(conn)
    already_done = get_already_crawled(conn) if resume else set()

    todo = [p for p in pools if p["pool_id"] not in already_done]
    if max_pools:
        todo = todo[:max_pools]

    total = len(todo)
    print(f"\n📊 Yield History Crawler")
    print(f"   Totalt: {len(pools)} pooler")
    print(f"   Redan crawlade: {len(already_done)}")
    print(f"   Att crawla: {total}")
    print(f"   Lookback: {LOOKBACK_DAYS} dagar")
    print(f"   Rate limit: {1/RATE_LIMIT:.0f} req/sek")
    print(f"   Estimerad tid: ~{total * RATE_LIMIT / 60:.0f} min\n")

    start_time = time.time()
    success = 0
    failed = 0
    total_rows = 0

    for i, pool in enumerate(todo):
        pool_id = pool["pool_id"]
        project = pool["project"]
        symbol = pool["symbol"]

        history = fetch_pool_history(pool_id)

        if history is not None:
            rows_saved = save_history(conn, pool_id, history)
            total_rows += rows_saved
            success += 1
        else:
            failed += 1

        # Progress print var 50:e pool
        if (i + 1) % 50 == 0 or (i + 1) == total:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (total - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1:5}/{total}] ✅ {success} ❌ {failed} | "
                  f"{total_rows:,} rows | "
                  f"{rate:.1f} req/s | "
                  f"~{remaining/60:.1f} min kvar")

        # Commit var BATCH_COMMIT:e pool
        if (i + 1) % BATCH_COMMIT == 0:
            conn.commit()

        time.sleep(RATE_LIMIT)

    conn.commit()
    conn.close()

    elapsed = time.time() - start_time
    print(f"\n✅ KLAR!")
    print(f"   Crawlade: {success}/{total}")
    print(f"   Misslyckade: {failed}")
    print(f"   Totalt sparade rader: {total_rows:,}")
    print(f"   Tid: {elapsed/60:.1f} min")


if __name__ == "__main__":
    import sys
    # python3 yield_history_crawler.py          → alla pooler
    # python3 yield_history_crawler.py 100      → testa med 100 pooler
    max_p = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_crawler(resume=True, max_pools=max_p)
