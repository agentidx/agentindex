#!/usr/bin/env python3
"""
404-driven /token/<slug> coverage backfill.

Source: AUDIT-QUERY-20260418 finding #4, follow-up FU-QUERY-20260418-04.

The /token/<slug> route returns 404 for ~20% of 7d traffic (4423/22135).
The slugs that 404 are overwhelmingly long-tail memecoins and niche DeFi
governance tokens. They are already registered in token_slugs.json, but
they have no rows in crypto_rating_daily / crypto_ndd_daily /
nerq_risk_signals, so _render_token_page returns None -> 404.

This job is a miss-log consumer:
  1. Query the Smedjan analytics_mirror for slugs that 404 >= N times / 7d.
  2. Skip slugs that already have nerq_risk_signals rows (work already
     done by the main pipeline) or that a prior run marked dead.
  3. For each candidate, try CoinGecko free-tier
     /coins/{id}/market_chart + /coins/{id} to bring in price history.
  4. Fall back to DexScreener /dex/search?q=<slug> if CoinGecko 404s.
  5. Write crypto_price_history + a minimal crypto_rating_daily +
     nerq_risk_signals row (details.source = "404_backfill") so the
     /token/<slug> page renders next request.
  6. Log every attempt to nerq_coverage_ingest_log for audit + to avoid
     re-probing dead slugs every run.

Strictly free-tier (no paid APIs). Rate-limited: 2s between CoinGecko
calls (free tier is ~30 req/min; we stay well under). DexScreener: 1s.

Usage:
  python3 token_coverage_backfill.py                    # default run
  python3 token_coverage_backfill.py --dry-run          # no writes
  python3 token_coverage_backfill.py --limit 10
  python3 token_coverage_backfill.py --min-hits 3 --days 7

Schedule: once daily via launchd or cron after the main pipeline
finishes. Don't run it more than 1x/day - the 404 log is 7-day-rolling
so daily is enough.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")
SLUGS_PATH = os.path.join(SCRIPT_DIR, "token_slugs.json")

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEXSCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/search"

COINGECKO_DELAY_SEC = 2.0
DEXSCREENER_DELAY_SEC = 1.0
HTTP_TIMEOUT = 20

LOG_FMT = "%(asctime)s | %(levelname)-5s | %(message)s"
logging.basicConfig(format=LOG_FMT, level=logging.INFO, datefmt="%H:%M:%S")
log = logging.getLogger("token_coverage_backfill")

BACKFILL_SOURCE_TAG = "404_backfill"

# Re-probe a slug we previously marked dead only after this many days
# (lets us recover from a transient CoinGecko listing-race).
DEAD_SLUG_COOLDOWN_DAYS = 30


def ensure_ingest_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nerq_coverage_ingest_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            hits_7d INTEGER,
            source TEXT,
            status TEXT NOT NULL,
            http_status INTEGER,
            note TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_coverage_log_token_attempted
            ON nerq_coverage_ingest_log(token_id, attempted_at)
        """
    )
    conn.commit()


def load_404_candidates(min_hits: int, days: int, limit: int) -> list[tuple[str, int]]:
    """Return [(token_id, hits_7d)] from the Smedjan analytics mirror."""
    try:
        from smedjan import sources
    except ImportError:
        log.error(
            "smedjan package not on PYTHONPATH; cannot read analytics_mirror. "
            "Set PYTHONPATH=/Users/anstudio/agentindex and source smedjan .env."
        )
        return []

    sql = """
        SELECT substring(path FROM '^/token/([^/]+)$') AS slug,
               count(*) AS hits
        FROM analytics_mirror.requests
        WHERE ts > now() - interval %s
          AND status = 404
          AND path ~ '^/token/[^/]+$'
        GROUP BY slug
        HAVING count(*) >= %s
        ORDER BY hits DESC
        LIMIT %s
    """
    interval = f"{days} days"
    try:
        with sources.analytics_mirror_cursor() as (_, cur):
            cur.execute(sql, (interval, min_hits, limit))
            rows = cur.fetchall()
    except Exception as e:  # SourceUnavailable or psycopg2 errors
        log.error("Failed to query analytics_mirror: %s", e)
        return []

    return [(slug, int(hits)) for slug, hits in rows if slug]


def already_has_signal(conn: sqlite3.Connection, token_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM nerq_risk_signals WHERE token_id = ? LIMIT 1",
        (token_id,),
    ).fetchone()
    return row is not None


def recently_marked_dead(conn: sqlite3.Connection, token_id: str) -> bool:
    row = conn.execute(
        """
        SELECT attempted_at FROM nerq_coverage_ingest_log
        WHERE token_id = ? AND status IN ('not_found', 'error')
        ORDER BY attempted_at DESC LIMIT 1
        """,
        (token_id,),
    ).fetchone()
    if not row:
        return False
    try:
        last = datetime.fromisoformat(row[0])
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last).days < DEAD_SLUG_COOLDOWN_DAYS


def _http_get(url: str, params: Optional[dict] = None) -> tuple[int, Optional[dict]]:
    try:
        import requests
    except ImportError:
        log.error("requests not installed; cannot reach external APIs")
        return 0, None
    try:
        r = requests.get(
            url,
            params=params or {},
            timeout=HTTP_TIMEOUT,
            headers={"Accept": "application/json", "User-Agent": "nerq-coverage-backfill/1.0"},
        )
    except Exception as e:
        log.debug("GET %s failed: %s", url, e)
        return 0, None
    if r.status_code != 200:
        return r.status_code, None
    try:
        return 200, r.json()
    except ValueError:
        return 200, None


def fetch_coingecko_token(token_id: str) -> Optional[dict]:
    """Return {meta, history} from CoinGecko free tier, or None."""
    status, meta = _http_get(
        f"{COINGECKO_BASE}/coins/{token_id}",
        {
            "localization": "false",
            "tickers": "false",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        },
    )
    if status != 200 or not isinstance(meta, dict):
        return None

    time.sleep(COINGECKO_DELAY_SEC)

    status2, history = _http_get(
        f"{COINGECKO_BASE}/coins/{token_id}/market_chart",
        {"vs_currency": "usd", "days": 90, "interval": "daily"},
    )
    if status2 != 200 or not isinstance(history, dict):
        history = None

    return {"meta": meta, "history": history}


def fetch_dexscreener_token(slug: str) -> Optional[dict]:
    """DexScreener doesn't track history deeply; return the best match pair."""
    q = slug.replace("-", " ")
    status, data = _http_get(DEXSCREENER_SEARCH, {"q": q})
    if status != 200 or not isinstance(data, dict):
        return None
    pairs = data.get("pairs") or []
    if not pairs:
        return None
    # Pick highest-liquidity pair matching the slug (loose match on base symbol/name)
    slug_norm = slug.replace("-", "").lower()
    ranked = []
    for p in pairs:
        base = p.get("baseToken") or {}
        sym = (base.get("symbol") or "").lower()
        name = (base.get("name") or "").replace(" ", "").lower()
        if sym == slug_norm or name == slug_norm or slug_norm in name:
            liq = (p.get("liquidity") or {}).get("usd") or 0
            ranked.append((liq, p))
    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0] or 0, reverse=True)
    return {"pair": ranked[0][1]}


# ---- risk synthesis ------------------------------------------------------


def _safe_mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def synthesize_signal(token_id: str, cg_data: Optional[dict], dex_data: Optional[dict]) -> dict:
    """
    Turn thin CoinGecko / DexScreener payloads into a conservative
    nerq_risk_signals row. The main pipeline will recompute a real signal
    the next day - this is just a "first-touch" scaffold so the page stops
    404-ing.
    """
    out = {
        "token_id": token_id,
        "signal_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "btc_beta": None,
        "vol_30d": None,
        "trust_p3": None,
        "trust_score": None,
        "sig6_structure": None,
        "ndd_current": None,
        "ndd_min_4w": None,
        "p3_decay_3m": None,
        "score_decay_3m": None,
        "structural_weakness": 2,  # Conservative default (unknown thin-data tokens)
        "structural_strength": 0,
        "risk_level": "WATCH",
        "drawdown_90d": None,
        "weeks_since_ath": None,
        "excess_vol": None,
        "p3_rank": None,
        "details": {},
    }

    prices_90d: list[float] = []
    market_cap = None
    symbol = None
    name = None
    mcap_rank = None
    change_24h = None
    change_30d = None
    current_price = None

    if cg_data:
        meta = cg_data.get("meta") or {}
        hist = cg_data.get("history") or {}
        market_data = meta.get("market_data") or {}
        symbol = (meta.get("symbol") or "").upper() or None
        name = meta.get("name")
        mcap_rank = meta.get("market_cap_rank")
        current_price = (market_data.get("current_price") or {}).get("usd")
        market_cap = (market_data.get("market_cap") or {}).get("usd")
        change_24h = (market_data.get("price_change_percentage_24h_in_currency") or {}).get("usd")
        change_30d = (market_data.get("price_change_percentage_30d_in_currency") or {}).get("usd")
        prices = hist.get("prices") or []
        prices_90d = [p[1] for p in prices if p and p[1] and p[1] > 0]

    if not prices_90d and dex_data:
        pair = dex_data.get("pair") or {}
        base = pair.get("baseToken") or {}
        symbol = symbol or (base.get("symbol") or "").upper() or None
        name = name or base.get("name")
        try:
            current_price = float(pair.get("priceUsd")) if pair.get("priceUsd") else current_price
        except (TypeError, ValueError):
            pass
        market_cap = market_cap or pair.get("marketCap") or pair.get("fdv")
        change_24h = change_24h or (pair.get("priceChange") or {}).get("h24")

    # Volatility + drawdown from prices_90d if we have enough points
    if len(prices_90d) >= 30:
        rets = []
        for i in range(1, len(prices_90d)):
            prev, cur = prices_90d[i - 1], prices_90d[i]
            if prev > 0:
                rets.append((cur - prev) / prev)
        if len(rets) >= 20:
            mu = sum(rets) / len(rets)
            var = sum((r - mu) ** 2 for r in rets) / len(rets)
            out["vol_30d"] = round(math.sqrt(var) * math.sqrt(365), 4)
        peak = max(prices_90d)
        trough = min(prices_90d[prices_90d.index(peak):]) if peak else None
        if peak and trough and peak > 0:
            out["drawdown_90d"] = round((trough - peak) / peak * 100.0, 2)

    # Trust score heuristic: market-cap rank is the strongest free signal.
    if mcap_rank:
        if mcap_rank <= 50:
            score = 60
        elif mcap_rank <= 200:
            score = 50
        elif mcap_rank <= 500:
            score = 42
        else:
            score = 35
    elif market_cap:
        if market_cap >= 1e9:
            score = 55
        elif market_cap >= 1e8:
            score = 45
        elif market_cap >= 1e7:
            score = 38
        elif market_cap >= 1e6:
            score = 30
        else:
            score = 25
    else:
        score = 25  # DexScreener hit, no market cap known -> very thin

    # Penalize on big drawdown / extreme vol
    if out["drawdown_90d"] is not None and out["drawdown_90d"] <= -60:
        score -= 8
    if out["vol_30d"] is not None and out["vol_30d"] >= 2.0:
        score -= 5

    score = max(10, min(80, score))
    out["trust_score"] = float(score)
    out["trust_p3"] = float(score)  # thin-data: align p3 with overall score

    # Risk-level classification
    sw_flags = 0
    strength = 0
    if score < 35:
        sw_flags += 1
    if out["drawdown_90d"] is not None and out["drawdown_90d"] <= -50:
        sw_flags += 1
    if out["vol_30d"] is not None and out["vol_30d"] >= 1.5:
        sw_flags += 1
    if mcap_rank and mcap_rank <= 200:
        strength += 1
    out["structural_weakness"] = sw_flags
    out["structural_strength"] = strength

    if sw_flags >= 3 or score < 25:
        out["risk_level"] = "CRITICAL"
    elif sw_flags >= 2 or score < 35:
        out["risk_level"] = "WARNING"
    elif sw_flags >= 1:
        out["risk_level"] = "WATCH"
    else:
        out["risk_level"] = "WATCH"  # thin data -> never SAFE

    out["details"] = {
        "source": BACKFILL_SOURCE_TAG,
        "ingest_source": "coingecko" if cg_data else ("dexscreener" if dex_data else None),
        "symbol": symbol,
        "name": name,
        "market_cap_rank": mcap_rank,
        "market_cap_usd": market_cap,
        "current_price_usd": current_price,
        "price_change_24h": change_24h,
        "price_change_30d": change_30d,
        "vol_30d": out["vol_30d"],
        "dd_90d": out["drawdown_90d"],
        "history_points": len(prices_90d),
        "score_heuristic": score,
    }
    return out


def write_signal(conn: sqlite3.Connection, signal: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO nerq_risk_signals
        (token_id, signal_date, btc_beta, vol_30d, trust_p3, trust_score,
         sig6_structure, ndd_current, ndd_min_4w, p3_decay_3m, score_decay_3m,
         structural_weakness, structural_strength, risk_level, drawdown_90d,
         weeks_since_ath, excess_vol, p3_rank, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal["token_id"],
            signal["signal_date"],
            signal["btc_beta"],
            signal["vol_30d"],
            signal["trust_p3"],
            signal["trust_score"],
            signal["sig6_structure"],
            signal["ndd_current"],
            signal["ndd_min_4w"],
            signal["p3_decay_3m"],
            signal["score_decay_3m"],
            signal["structural_weakness"],
            signal["structural_strength"],
            signal["risk_level"],
            signal["drawdown_90d"],
            signal["weeks_since_ath"],
            signal["excess_vol"],
            signal["p3_rank"],
            json.dumps(signal["details"]),
        ),
    )


def write_ndd(conn: sqlite3.Connection, token_id: str, signal: dict) -> None:
    """
    Write a minimal crypto_ndd_daily row so _render_token_page takes the
    T4 risk-signal path (not the T1 rating template - that path assumes
    full pillar data and crash_probability, which we don't have).

    Intentionally leave crash_probability NULL; the risk-signal renderer
    handles NULL -> "N/A" gracefully.
    """
    details = signal["details"]
    run_date = signal["signal_date"]
    now_iso = datetime.now(timezone.utc).isoformat()
    risk_level = signal["risk_level"]

    conn.execute(
        """
        INSERT OR REPLACE INTO crypto_ndd_daily
        (run_date, token_id, symbol, name, market_cap_rank, trust_grade,
         ndd, signal_1, signal_2, signal_3, signal_4, signal_5, signal_6, signal_7,
         alert_level, override_triggered, confirmed_distress, has_ohlcv,
         price_usd, market_cap, volume_24h, breakdown, calculated_at,
         ndd_trend, ndd_change_4w, crash_probability,
         hc_alert, hc_streak, bottlefish_signal, bounce_90d)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_date,
            token_id,
            details.get("symbol"),
            details.get("name"),
            details.get("market_cap_rank"),
            "NR",
            0.0,  # ndd placeholder; real pipeline will overwrite
            None, None, None, None, None, None, None,
            risk_level,
            0, 0, 0,
            details.get("current_price_usd"),
            details.get("market_cap_usd"),
            None,
            json.dumps({"source": BACKFILL_SOURCE_TAG, "rationale": "thin-data 404 backfill scaffold"}),
            now_iso,
            None, None, None,
            0, 0, None, None,
        ),
    )


def write_price_history(conn: sqlite3.Connection, token_id: str, cg_data: Optional[dict]) -> int:
    if not cg_data:
        return 0
    hist = cg_data.get("history") or {}
    prices = hist.get("prices") or []
    volumes = {int(v[0]): v[1] for v in (hist.get("total_volumes") or []) if v and v[0] is not None}
    mcaps = {int(m[0]): m[1] for m in (hist.get("market_caps") or []) if m and m[0] is not None}
    fetched_at = datetime.now(timezone.utc).isoformat()
    n = 0
    for ts_ms, price in prices:
        if ts_ms is None or price is None or price <= 0:
            continue
        date = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
        vol = volumes.get(int(ts_ms))
        mcap = mcaps.get(int(ts_ms))
        conn.execute(
            """
            INSERT OR IGNORE INTO crypto_price_history
            (token_id, date, open, high, low, close, volume, market_cap, fetched_at, source)
            VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?, ?, 'coingecko')
            """,
            (token_id, date, float(price), vol, mcap, fetched_at),
        )
        n += 1
    return n


def log_attempt(
    conn: sqlite3.Connection,
    token_id: str,
    hits: int,
    source: Optional[str],
    status: str,
    http_status: Optional[int] = None,
    note: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO nerq_coverage_ingest_log
        (token_id, attempted_at, hits_7d, source, status, http_status, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token_id,
            datetime.now(timezone.utc).isoformat(),
            hits,
            source,
            status,
            http_status,
            note,
        ),
    )


def update_slugs_json(token_id: str, details: dict) -> bool:
    """Refresh name/symbol and promote tier on token_slugs.json so the
    /token/<slug> route actually renders the page. The 404 is double-gated:
    (a) _render_token_page has an ENABLED_TIERS = {T1,T2,T4} gate, (b) no
    rating rows exist. We handle (b) by writing signals; this handles (a)
    by moving the slug from its default T5 into T4 (thin-data tier)."""
    try:
        with open(SLUGS_PATH) as f:
            slugs = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(slugs, dict):
        return False
    existed = token_id in slugs
    current = slugs.get(token_id) or {}
    changed = not existed  # new slug -> we must write the file
    for k_src, k_dst in [("name", "name"), ("symbol", "symbol")]:
        val = details.get(k_src)
        if val and not current.get(k_dst):
            current[k_dst] = val
            changed = True
    if current.get("tier") in (None, "T5"):
        current["tier"] = "T4"
        changed = True
    current.setdefault("risk_grade", "NR")
    if changed:
        slugs[token_id] = current
        tmp = SLUGS_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(slugs, f, separators=(",", ":"))
        os.replace(tmp, SLUGS_PATH)
    return changed


def process_candidate(
    conn: sqlite3.Connection,
    token_id: str,
    hits: int,
    dry_run: bool,
) -> str:
    """Return a short status string for logging."""
    cg = fetch_coingecko_token(token_id)
    time.sleep(COINGECKO_DELAY_SEC)

    dex = None
    if not cg:
        dex = fetch_dexscreener_token(token_id)
        time.sleep(DEXSCREENER_DELAY_SEC)

    if not cg and not dex:
        if not dry_run:
            log_attempt(conn, token_id, hits, None, "not_found", http_status=404,
                        note="coingecko 404 + dexscreener no match")
            conn.commit()
        return "not_found"

    signal = synthesize_signal(token_id, cg, dex)
    source_used = signal["details"].get("ingest_source")

    if dry_run:
        log.info(
            "[DRY] %-30s hits=%-3d src=%-11s score=%.1f risk=%s hist=%d",
            token_id,
            hits,
            source_used,
            signal["trust_score"] or 0,
            signal["risk_level"],
            signal["details"].get("history_points") or 0,
        )
        return "dry_run"

    write_signal(conn, signal)
    write_ndd(conn, token_id, signal)
    rows = write_price_history(conn, token_id, cg) if cg else 0
    log_attempt(
        conn,
        token_id,
        hits,
        source_used,
        "ingested",
        http_status=200,
        note=f"history_points={rows}",
    )
    conn.commit()

    update_slugs_json(token_id, signal["details"])

    log.info(
        "INGESTED %-30s hits=%-3d src=%-11s score=%.1f risk=%s hist_rows=%d",
        token_id,
        hits,
        source_used,
        signal["trust_score"] or 0,
        signal["risk_level"],
        rows,
    )
    return "ingested"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-hits", type=int, default=2,
                        help="Minimum 404 hits in the window to consider a slug (default: 2)")
    parser.add_argument("--days", type=int, default=7,
                        help="Lookback window in days (default: 7)")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max candidates to process per run (default: 50)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen; do not write")
    parser.add_argument("--force", action="store_true",
                        help="Re-probe slugs marked dead within cooldown")
    args = parser.parse_args()

    log.info("404-driven /token/<slug> coverage backfill (min_hits=%d days=%d limit=%d dry_run=%s)",
             args.min_hits, args.days, args.limit, args.dry_run)

    candidates = load_404_candidates(args.min_hits, args.days, args.limit * 3)
    if not candidates:
        log.info("No 404 candidates from analytics_mirror; exiting.")
        return 0

    log.info("Fetched %d raw candidates from 404 log", len(candidates))

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_ingest_log_table(conn)

        queued: list[tuple[str, int]] = []
        for slug, hits in candidates:
            if already_has_signal(conn, slug):
                continue
            if not args.force and recently_marked_dead(conn, slug):
                continue
            queued.append((slug, hits))
            if len(queued) >= args.limit:
                break

        log.info("Queued %d candidates (after filter: present, cooldown)", len(queued))

        stats = {"ingested": 0, "not_found": 0, "dry_run": 0, "error": 0}
        for slug, hits in queued:
            try:
                result = process_candidate(conn, slug, hits, args.dry_run)
            except Exception as e:
                log.error("ERROR processing %s: %s", slug, e)
                try:
                    if not args.dry_run:
                        log_attempt(conn, slug, hits, None, "error", note=str(e)[:200])
                        conn.commit()
                except Exception:
                    pass
                stats["error"] += 1
                continue
            stats[result] = stats.get(result, 0) + 1

        log.info("Done: %s", stats)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
