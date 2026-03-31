#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 2.5: API v2 Router
Complete v1/ API with all crypto endpoints.
"""

import sqlite3
import os
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

DB_NAME = "crypto_trust.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
API_VERSION = "2.0.0"

CACHE_RATINGS = {}
CACHE_SIGNALS = {}
CACHE_SAFETY = {}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def latest_run_date(conn, table="crypto_rating_daily"):
    col = "signal_date" if table == "nerq_risk_signals" else "run_date"
    row = conn.execute(f"SELECT MAX({col}) as d FROM {table}").fetchone()
    return row["d"] if row else None


def wrap_response(data, meta=None):
    result = {"data": data, "meta": {"api_version": API_VERSION, "timestamp": datetime.utcnow().isoformat() + "Z"}}
    if meta:
        result["meta"].update(meta)
    return result


def parse_json_field(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except:
        return {}


def add_cache(response, seconds):
    response.headers["Cache-Control"] = f"public, max-age={seconds}"


router_v1 = APIRouter(prefix="/v1/crypto", tags=["crypto-v1"])


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/rating/{token_id}
# ─────────────────────────────────────────────────────────────
@router_v1.get("/rating/{token_id}")
def get_rating(token_id: str, response: Response):
    """Get Trust Score rating"""
    conn = get_db()
    run_date = latest_run_date(conn)

    if run_date:
        row = conn.execute("""
            SELECT token_id, symbol, name, market_cap_rank, rating, score,
                   pillar_1, pillar_2, pillar_3, pillar_4, pillar_5,
                   breakdown, price_usd, market_cap, volume_24h,
                   price_change_24h, price_change_7d, price_change_30d,
                   run_date, calculated_at
            FROM crypto_rating_daily WHERE token_id = ? AND run_date = ?
        """, (token_id, run_date)).fetchone()
    else:
        row = conn.execute("""
            SELECT token_id, '' as symbol, '' as name, 0 as market_cap_rank,
                   rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5,
                   breakdown, 0 as price_usd, 0 as market_cap, 0 as volume_24h,
                   0 as price_change_24h, 0 as price_change_7d, 0 as price_change_30d,
                   year_month as run_date, calculated_at
            FROM crypto_rating_history WHERE token_id = ? ORDER BY year_month DESC LIMIT 1
        """, (token_id,)).fetchone()

    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Token '{token_id}' not found")

    data = dict(row)
    breakdown = parse_json_field(data.pop("breakdown", None))
    data["breakdown"] = breakdown
    data["pillars"] = {
        "security": data.get("pillar_1"),
        "compliance": data.get("pillar_2"),
        "maintenance": data.get("pillar_3"),
        "popularity": data.get("pillar_4"),
        "ecosystem": data.get("pillar_5"),
    }
    score = data.get("score", 0)
    data["summary"] = f"According to Nerq's Crypto Trust Score, {token_id} is rated {data.get('rating')} with a composite score of {score:.1f}/100 as of {data.get('run_date')}."

    add_cache(response, 300)
    return wrap_response(data, {"run_date": run_date})


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/ndd/{token_id}
# ─────────────────────────────────────────────────────────────
@router_v1.get("/ndd/{token_id}")
def get_ndd(token_id: str, response: Response):
    """Get NDD distress score"""
    conn = get_db()
    run_date = latest_run_date(conn, "crypto_ndd_daily")

    if run_date:
        row = conn.execute("""
            SELECT token_id, symbol, name, market_cap_rank, trust_grade,
                   ndd, signal_1, signal_2, signal_3, signal_4, signal_5, signal_6, signal_7,
                   alert_level, ndd_trend, ndd_change_4w,
                   crash_probability, hc_alert, hc_streak, bottlefish_signal, bounce_90d,
                   run_date, calculated_at
            FROM crypto_ndd_daily WHERE token_id = ? AND run_date = ?
        """, (token_id, run_date)).fetchone()
    else:
        row = conn.execute("""
            SELECT token_id, '' as symbol, '' as name, 0 as market_cap_rank, '' as trust_grade,
                   ndd, signal_1, signal_2, signal_3, signal_4, signal_5, signal_6, signal_7,
                   alert_level, '' as ndd_trend, 0 as ndd_change_4w,
                   0 as crash_probability, 0 as hc_alert, 0 as hc_streak,
                   '' as bottlefish_signal, 0 as bounce_90d,
                   week_date as run_date, calculated_at
            FROM crypto_ndd_history WHERE token_id = ? ORDER BY week_date DESC LIMIT 1
        """, (token_id,)).fetchone()

    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Token '{token_id}' not found")

    data = dict(row)
    ndd = data.get("ndd", 0)
    cp = data.get("crash_probability", 0)
    grade = data.get("trust_grade", "")
    data["summary"] = f"{token_id} has NDD {ndd:.2f} (Alert: {data.get('alert_level')}, Grade: {grade}). Crash probability (90d): {cp:.0%}"

    add_cache(response, 300)
    return wrap_response(data, {"run_date": run_date})


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/ratings
# ─────────────────────────────────────────────────────────────
@router_v1.get("/ratings")
def get_ratings(
    response: Response,
    sort: str = Query("score", description="Sort field"),
    order: str = Query("desc", description="asc or desc"),
    rating_class: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = Query(200, le=500),
    offset: int = Query(0),
):
    """Get all ratings"""
    conn = get_db()
    run_date = latest_run_date(conn)

    if not run_date:
        conn.close()
        raise HTTPException(status_code=503, detail="No rating data available")

    sort_col = {"score": "r.score", "rank": "r.market_cap_rank", "name": "r.token_id"}.get(sort, "r.score")
    order_dir = "ASC" if order.lower() == "asc" else "DESC"

    query = f"""
        SELECT r.token_id, r.symbol, r.name, r.market_cap_rank, r.rating, r.score,
               r.pillar_1, r.pillar_2, r.pillar_3, r.pillar_4, r.pillar_5,
               r.price_usd, r.market_cap, r.volume_24h,
               r.price_change_24h, r.price_change_7d, r.price_change_30d,
               s.risk_level, s.structural_weakness, s.structural_strength
        FROM crypto_rating_daily r
        LEFT JOIN nerq_risk_signals s ON r.token_id = s.token_id AND s.signal_date = r.run_date
        WHERE r.run_date = ? ORDER BY {sort_col} {order_dir}
    """

    rows = conn.execute(query, (run_date,)).fetchall()
    conn.close()

    results = [dict(r) for r in rows]

    if rating_class:
        results = [r for r in results if r.get("rating", "").startswith(rating_class)]
    if risk_level:
        results = [r for r in results if r.get("risk_level") == risk_level]

    total = len(results)
    results = results[offset:offset+limit]

    add_cache(response, 300)
    return wrap_response(results, {"run_date": run_date, "total": total, "limit": limit, "offset": offset})


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/signals
# ─────────────────────────────────────────────────────────────
@router_v1.get("/signals")
def get_signals(response: Response, level: Optional[str] = None, limit: int = Query(50, le=200)):
    """Get active risk signals"""
    conn = get_db()
    run_date = latest_run_date(conn, "nerq_risk_signals")
    if not run_date:
        conn.close()
        return wrap_response([])

    query = """
        SELECT s.token_id, s.signal_date, s.risk_level, s.structural_weakness,
               s.structural_strength, s.btc_beta, s.vol_30d, s.ndd_current,
               s.ndd_min_4w, s.trust_p3, s.trust_score, s.drawdown_90d, s.details,
               n.hc_alert, n.hc_streak, n.bottlefish_signal, n.crash_probability,
               n.symbol, n.name, n.market_cap_rank,
               r.rating, r.score as trust_score_total
        FROM nerq_risk_signals s
        LEFT JOIN crypto_ndd_daily n ON s.token_id = n.token_id AND n.run_date = s.signal_date
        LEFT JOIN crypto_rating_daily r ON s.token_id = r.token_id AND r.run_date = s.signal_date
        WHERE s.signal_date = ? AND s.risk_level IN ('WARNING', 'CRITICAL')
    """
    params = [run_date]
    if level:
        query += " AND s.risk_level = ?"
        params.append(level)
    query += " ORDER BY s.structural_weakness DESC, s.ndd_current ASC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = [dict(r) for r in rows]
    for r in results:
        r["details"] = parse_json_field(r.get("details"))

    add_cache(response, 300)
    return wrap_response(results, {"run_date": run_date, "total": len(results)})


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/signals/history
# ─────────────────────────────────────────────────────────────
@router_v1.get("/signals/history")
def get_signals_history(response: Response, token_id: Optional[str] = None, days: int = Query(30), limit: int = Query(100, le=500)):
    """Historical signals with outcomes"""
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    query = """
        SELECT s.token_id, s.signal_date, s.risk_level, s.structural_weakness,
               s.ndd_current, s.trust_p3, s.drawdown_90d, s.details,
               n.hc_alert, n.crash_probability, n.symbol, n.name
        FROM nerq_risk_signals s
        LEFT JOIN crypto_ndd_daily n ON s.token_id = n.token_id AND n.run_date = s.signal_date
        WHERE s.signal_date >= ? AND s.risk_level IN ('WARNING', 'CRITICAL')
    """
    params = [cutoff]
    if token_id:
        query += " AND s.token_id = ?"
        params.append(token_id)
    query += " ORDER BY s.signal_date DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()

    # Add outcome data (did a crash happen within 90 days?)
    results = []
    for r in rows:
        d = dict(r)
        d["details"] = parse_json_field(d.get("details"))

        # Check outcome
        outcome_row = conn.execute("""
            SELECT MIN(close) as min_p, MAX(close) as ref_p FROM crypto_price_history
            WHERE token_id = ? AND date BETWEEN ? AND date(?, '+90 days')
        """, (d["token_id"], d["signal_date"], d["signal_date"])).fetchone()

        if outcome_row and outcome_row["ref_p"] and outcome_row["ref_p"] > 0:
            d["outcome_max_drawdown"] = round((outcome_row["min_p"] - outcome_row["ref_p"]) / outcome_row["ref_p"], 4)
        else:
            d["outcome_max_drawdown"] = None

        results.append(d)

    conn.close()

    add_cache(response, 600)
    return wrap_response(results, {"total": len(results), "days": days})


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/compare/{token1}/{token2}
# ─────────────────────────────────────────────────────────────
@router_v1.get("/compare/{token1}/{token2}")
def compare_tokens(token1: str, token2: str, response: Response):
    """Compare two tokens"""
    conn = get_db()
    run_date = latest_run_date(conn)

    def get_token_data(tid):
        if run_date:
            row = conn.execute(
                "SELECT token_id, symbol, name, rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5, price_usd, market_cap FROM crypto_rating_daily WHERE token_id = ? AND run_date = ?",
                (tid, run_date)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT token_id, '' as symbol, '' as name, rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5, 0 as price_usd, 0 as market_cap FROM crypto_rating_history WHERE token_id = ? ORDER BY year_month DESC LIMIT 1",
                (tid,)
            ).fetchone()

        if not row:
            return None

        data = dict(row)

        ndd_row = conn.execute(
            "SELECT ndd, alert_level, crash_probability FROM crypto_ndd_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1",
            (tid,)
        ).fetchone()
        if ndd_row:
            data.update(dict(ndd_row))

        sig_row = conn.execute(
            "SELECT risk_level, structural_weakness FROM nerq_risk_signals WHERE token_id = ? ORDER BY signal_date DESC LIMIT 1",
            (tid,)
        ).fetchone()
        if sig_row:
            data.update(dict(sig_row))

        return data

    t1 = get_token_data(token1)
    t2 = get_token_data(token2)
    conn.close()

    if not t1:
        raise HTTPException(status_code=404, detail=f"Token '{token1}' not found")
    if not t2:
        raise HTTPException(status_code=404, detail=f"Token '{token2}' not found")

    # Determine winner per pillar
    comparison = {}
    for p in ["pillar_1", "pillar_2", "pillar_3", "pillar_4", "pillar_5"]:
        v1 = t1.get(p, 0) or 0
        v2 = t2.get(p, 0) or 0
        comparison[p] = {"token1": v1, "token2": v2, "winner": token1 if v1 >= v2 else token2}

    add_cache(response, 300)
    return wrap_response({
        "token1": t1,
        "token2": t2,
        "comparison": comparison,
        "overall_winner": token1 if (t1.get("score", 0) or 0) >= (t2.get("score", 0) or 0) else token2,
    })


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/distress-watch
# ─────────────────────────────────────────────────────────────
@router_v1.get("/distress-watch")
def get_distress_watch(response: Response):
    """Distress watchlist (NDD < 2.0)"""
    conn = get_db()
    run_date = latest_run_date(conn, "crypto_ndd_daily")
    if not run_date:
        conn.close()
        return wrap_response([])

    rows = conn.execute("""
        SELECT d.token_id, d.symbol, d.name, d.market_cap_rank,
               d.ndd, d.alert_level, d.crash_probability, d.hc_alert, d.bottlefish_signal,
               r.rating, r.score, r.price_usd, s.risk_level, s.structural_weakness
        FROM crypto_ndd_daily d
        LEFT JOIN crypto_rating_daily r ON d.token_id = r.token_id AND r.run_date = d.run_date
        LEFT JOIN nerq_risk_signals s ON d.token_id = s.token_id AND s.signal_date = d.run_date
        WHERE d.run_date = ? AND d.ndd < 2.0 ORDER BY d.ndd ASC
    """, (run_date,)).fetchall()
    conn.close()

    results = [dict(r) for r in rows]
    add_cache(response, 300)
    return wrap_response(results, {"run_date": run_date, "total": len(results)})


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/safety/{token_address}
# ─────────────────────────────────────────────────────────────
@router_v1.get("/safety/{token_address}")
def safety_check(token_address: str, response: Response):
    """Quick safety check (<100ms)"""
    conn = get_db()
    run_date = latest_run_date(conn)
    if not run_date:
        conn.close()
        raise HTTPException(status_code=503, detail="No data available")

    row = conn.execute("""
        SELECT r.token_id, r.symbol, r.name, r.rating, r.score, r.market_cap_rank,
               d.ndd, d.alert_level, d.crash_probability, d.hc_alert, d.hc_streak, d.bottlefish_signal,
               s.risk_level, s.structural_weakness, s.structural_strength
        FROM crypto_rating_daily r
        LEFT JOIN crypto_ndd_daily d ON r.token_id = d.token_id AND d.run_date = r.run_date
        LEFT JOIN nerq_risk_signals s ON r.token_id = s.token_id AND s.signal_date = r.run_date
        WHERE (r.token_id = ? OR r.symbol = ?) AND r.run_date = ? LIMIT 1
    """, (token_address, token_address.lower(), run_date)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Token '{token_address}' not found")

    data = dict(row)

    # Generate flags
    flags = []
    if data.get("crash_probability") and data["crash_probability"] > 0.3:
        flags.append("HIGH_CRASH_PROBABILITY")
    if data.get("structural_weakness") and data["structural_weakness"] >= 2:
        flags.append("STRUCTURAL_WEAKNESS_CRITICAL")
    elif data.get("structural_weakness") and data["structural_weakness"] >= 1:
        flags.append("STRUCTURAL_WEAKNESS_ELEVATED")
    if data.get("hc_alert"):
        flags.append("HC_ALERT_ACTIVE")

    data["flags"] = flags
    data["safe"] = len(flags) == 0

    add_cache(response, 60)
    return wrap_response(data)


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/risk-level/{token_id}
# ─────────────────────────────────────────────────────────────
@router_v1.get("/risk-level/{token_id}")
def get_risk_level(token_id: str, response: Response):
    """Risk classification"""
    conn = get_db()
    row = conn.execute("""
        SELECT token_id, signal_date, risk_level, btc_beta, vol_30d, trust_p3, trust_score,
               sig6_structure, ndd_current, ndd_min_4w, p3_decay_3m, score_decay_3m,
               structural_weakness, structural_strength, drawdown_90d, weeks_since_ath, details
        FROM nerq_risk_signals WHERE token_id = ? ORDER BY signal_date DESC LIMIT 1
    """, (token_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"No risk data for '{token_id}'")

    data = dict(row)
    data["details"] = parse_json_field(data.get("details"))

    # Classify
    sw = data.get("structural_weakness", 0) or 0
    p3 = data.get("trust_p3", 100) or 100
    if sw >= 2:
        data["classification"] = "CRITICAL"
    elif sw >= 1 or p3 < 50:
        data["classification"] = "weakness >= 1 OR p3 < 50"
    else:
        data["classification"] = "STABLE"

    add_cache(response, 300)
    return wrap_response(data)


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/risk-levels
# ─────────────────────────────────────────────────────────────
@router_v1.get("/risk-levels")
def get_risk_levels(response: Response, level: Optional[str] = None, sort: str = "weakness", limit: int = Query(200, le=500)):
    """All risk classifications"""
    conn = get_db()
    run_date = latest_run_date(conn, "nerq_risk_signals")
    if not run_date:
        conn.close()
        return wrap_response([])

    rows = conn.execute("""
        SELECT s.token_id, s.signal_date, s.risk_level, s.structural_weakness,
               s.structural_strength, s.ndd_current, s.trust_score, s.trust_p3,
               s.drawdown_90d, n.symbol, n.name, n.market_cap_rank,
               r.rating, r.score
        FROM nerq_risk_signals s
        LEFT JOIN crypto_ndd_daily n ON s.token_id = n.token_id AND n.run_date = s.signal_date
        LEFT JOIN crypto_rating_daily r ON s.token_id = r.token_id AND r.run_date = s.signal_date
        WHERE s.signal_date = ? ORDER BY s.structural_weakness DESC, s.ndd_current ASC
    """, (run_date,)).fetchall()

    # Distribution
    dist_rows = conn.execute(
        "SELECT risk_level, COUNT(*) as c FROM nerq_risk_signals WHERE signal_date = ? GROUP BY risk_level",
        (run_date,)
    ).fetchall()
    conn.close()

    results = [dict(r) for r in rows]
    if level:
        results = [r for r in results if r.get("risk_level") == level]

    distribution = {r["risk_level"]: r["c"] for r in dist_rows}

    add_cache(response, 300)
    return wrap_response(results[:limit], {"run_date": run_date, "total": len(results), "distribution": distribution})


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/portfolio/pairs
# ─────────────────────────────────────────────────────────────
@router_v1.get("/portfolio/pairs")
def get_pairs_portfolio(response: Response):
    """Pairs portfolio track record"""
    conn = get_db()
    rows = conn.execute("""
        SELECT month, regime, pairs_ret, n_pairs, pairs_status, pairs_detail, nav
        FROM crypto_portable_alpha_backtest WHERE variant = 'Growth' AND period = 'full_period'
        ORDER BY month DESC
    """).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        d["pairs_detail"] = parse_json_field(d.get("pairs_detail"))
        results.append(d)

    add_cache(response, 600)
    return wrap_response(results, {"total": len(results)})


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/portfolio/adaptive
# ─────────────────────────────────────────────────────────────
@router_v1.get("/portfolio/adaptive")
def get_adaptive_portfolio(response: Response):
    """Portable Alpha variants"""
    conn = get_db()
    rows = conn.execute("""
        SELECT variant, period, months, total_ret_pct, btc_total_ret_pct, alpha_pct,
               sharpe, btc_sharpe, max_dd_pct, btc_max_dd_pct, calmar, win_rate_pct, validation_score
        FROM crypto_portable_alpha_summary WHERE period = 'out_of_sample' ORDER BY variant
    """).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        # Get latest month data
        latest = conn.execute("""
            SELECT month, regime, btc_alloc, pairs_alloc, cash_alloc,
                   btc_ret, pairs_ret, port_ret, nav, btc_nav
            FROM crypto_portable_alpha_backtest WHERE variant = ? AND period = 'out_of_sample'
            ORDER BY month DESC LIMIT 1
        """, (d["variant"],)).fetchone()
        if latest:
            d["latest"] = dict(latest)
        results.append(d)

    conn.close()

    add_cache(response, 600)
    return wrap_response(results, {"total": len(results)})


# ─────────────────────────────────────────────────────────────
# PAPER TRADING ENDPOINTS
# ─────────────────────────────────────────────────────────────

PT_DB_NAME = "paper_trading.db"
PT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), PT_DB_NAME)


def get_pt_db():
    if not os.path.exists(PT_DB_PATH):
        raise HTTPException(status_code=503, detail="Paper trading not yet initialized")
    conn = sqlite3.connect(PT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router_v1.get("/paper-trading/nav/{portfolio}")
def get_paper_trading_nav(portfolio: str, response: Response):
    """Paper trading NAV history"""
    portfolio = portfolio.upper()
    if portfolio not in ("ALPHA", "DYNAMIC", "CONSERVATIVE"):
        raise HTTPException(status_code=400, detail="Portfolio must be ALPHA, DYNAMIC, or CONSERVATIVE")

    conn = get_pt_db()
    rows = conn.execute(
        "SELECT nav_date, nav_value, daily_return, cumulative_return, drawdown, max_drawdown, regime, btc_price, btc_nav FROM portfolio_nav WHERE portfolio = ? ORDER BY nav_date",
        (portfolio,)
    ).fetchall()
    conn.close()

    add_cache(response, 300)
    data_list = [dict(r) for r in rows]
    latest = data_list[-1] if data_list else {}
    days = len(data_list) - 1  # Day 0 = start, Day 1 = first trading day
    return wrap_response({"history": data_list, "latest": latest, "days": days}, {"portfolio": portfolio, "total": len(data_list)})


@router_v1.get("/paper-trading/positions/{portfolio}")
def get_paper_trading_positions(portfolio: str, response: Response):
    """Current paper trading positions"""
    portfolio = portfolio.upper()
    if portfolio not in ("ALPHA", "DYNAMIC", "CONSERVATIVE"):
        raise HTTPException(status_code=400, detail="Portfolio must be ALPHA, DYNAMIC, or CONSERVATIVE")

    conn = get_pt_db()
    rows = conn.execute(
        "SELECT signal_month, position_type, token_id, side, weight, entry_price, price_date, pair_index, conviction, composite_score, ndd_score FROM portfolio_positions WHERE portfolio = ? ORDER BY signal_month DESC, pair_index",
        (portfolio,)
    ).fetchall()
    conn.close()

    add_cache(response, 300)
    return wrap_response([dict(r) for r in rows], {"portfolio": portfolio, "total": len(rows)})


@router_v1.get("/paper-trading/signals")
def get_paper_trading_signals(response: Response):
    """All paper trading signals"""
    conn = get_pt_db()
    rows = conn.execute(
        "SELECT signal_date, signal_month, portfolio, regime, btc_monthly_return, btc_dd_from_ath, n_pairs, pairs_json, allocation_json FROM portfolio_signals ORDER BY signal_month DESC, portfolio"
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        d["pairs_json"] = parse_json_field(d.get("pairs_json"))
        d["allocation_json"] = parse_json_field(d.get("allocation_json"))
        results.append(d)

    add_cache(response, 300)
    return wrap_response(results, {"total": len(results)})


@router_v1.get("/paper-trading/regime")
def get_paper_trading_regime(response: Response):
    """Current market regime"""
    conn = get_pt_db()
    row = conn.execute(
        "SELECT check_date, btc_price, btc_ath_365d, btc_dd_from_ath, btc_monthly_return, alpha_regime, dynamic_regime FROM portfolio_regime ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not row:
        return wrap_response({})

    add_cache(response, 300)
    return wrap_response(dict(row))


# ─────────────────────────────────────────────────────────────
# GET /v1/crypto/alerts
# ─────────────────────────────────────────────────────────────
@router_v1.get("/alerts")
def get_alerts(
    response: Response,
    severity: Optional[str] = Query(None, description="Filter: critical, warning, distress"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Active risk alerts from NDD and structural weakness signals.
    Returns tokens with alert_level != 'SAFE' joined with structural weakness data.
    """
    conn = get_db()
    run_date = latest_run_date(conn, "crypto_ndd_daily")
    if not run_date:
        conn.close()
        return {
            "active_alerts": 0,
            "critical": 0,
            "warnings": 0,
            "alerts": [],
            "updated": datetime.utcnow().strftime("%Y-%m-%d"),
        }

    # Count by severity
    counts = conn.execute("""
        SELECT
            SUM(CASE WHEN n.alert_level IN ('DISTRESS') THEN 1 ELSE 0 END) as critical,
            SUM(CASE WHEN n.alert_level IN ('WARNING') THEN 1 ELSE 0 END) as warnings,
            SUM(CASE WHEN n.alert_level IN ('WATCH') THEN 1 ELSE 0 END) as watch
        FROM crypto_ndd_daily n
        WHERE n.run_date = ? AND n.alert_level != 'SAFE'
    """, [run_date]).fetchone()

    critical = counts["critical"] or 0
    warnings = counts["warnings"] or 0
    watch = counts["watch"] or 0
    total_alerts = critical + warnings + watch

    # Build query — join NDD with risk signals for structural weakness
    query = """
        SELECT n.token_id, n.name, n.symbol, n.alert_level, n.ndd, n.crash_probability,
               n.price_usd, n.market_cap, n.market_cap_rank, n.ndd_trend, n.hc_alert, n.hc_streak,
               s.structural_weakness, s.risk_level, s.trust_score, s.trust_p3, s.drawdown_90d
        FROM crypto_ndd_daily n
        LEFT JOIN nerq_risk_signals s ON n.token_id = s.token_id AND s.signal_date = n.run_date
        WHERE n.run_date = ? AND n.alert_level != 'SAFE'
    """
    params: list = [run_date]

    if severity:
        sev_map = {"critical": "DISTRESS", "warning": "WARNING", "distress": "DISTRESS", "watch": "WATCH"}
        mapped = sev_map.get(severity.lower())
        if mapped:
            query += " AND n.alert_level = ?"
            params.append(mapped)

    query += " ORDER BY n.ndd ASC, COALESCE(s.structural_weakness, 0) DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()

    alerts = []
    for r in rows:
        sw = r["structural_weakness"] or 0
        ndd_val = r["ndd"] or 0
        cp = r["crash_probability"] or 0

        # Determine alert type
        if r["alert_level"] == "DISTRESS":
            alert_type = "structural_collapse" if sw > 0.5 else "severe_distress"
            sev = "critical"
        elif r["alert_level"] == "WARNING":
            alert_type = "structural_weakness" if sw > 0.3 else "elevated_risk"
            sev = "warning"
        else:
            alert_type = "watch"
            sev = "watch"

        alerts.append({
            "token_id": r["token_id"],
            "name": r["name"] or r["token_id"],
            "symbol": r["symbol"] or "",
            "type": alert_type,
            "severity": sev,
            "alert_level": r["alert_level"],
            "crash_probability": round(cp, 4) if cp else None,
            "ndd": round(ndd_val, 4) if ndd_val else None,
            "trust_score": r["trust_score"],
            "structural_weakness": round(sw, 4) if sw else None,
            "ndd_trend": r["ndd_trend"],
            "market_cap_rank": r["market_cap_rank"],
        })

    add_cache(response, 300)
    return {
        "active_alerts": total_alerts,
        "critical": critical,
        "warnings": warnings,
        "watch": watch,
        "alerts": alerts,
        "updated": run_date,
    }


@router_v1.get("/paper-trading/audit")
def get_paper_trading_audit(response: Response):
    """Audit trail"""
    conn = get_pt_db()
    rows = conn.execute(
        "SELECT id, timestamp, event_type, data_hash, prev_hash FROM audit_log ORDER BY id"
    ).fetchall()
    conn.close()

    add_cache(response, 600)
    return wrap_response([dict(r) for r in rows], {"total": len(rows)})
