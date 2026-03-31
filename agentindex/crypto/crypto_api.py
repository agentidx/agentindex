#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 2.3: API Router
======================================
FastAPI router for all crypto endpoints.
Add to existing FastAPI app or run standalone.

Endpoints:
  GET /crypto/rating/{token_id}      — Current rating + breakdown
  GET /crypto/ndd/{token_id}         — Current NDD + trend (7d/30d)
  GET /crypto/ratings                — Top 200 ratings (sortable)
  GET /crypto/compare/{t1}/{t2}      — Compare two tokens
  GET /crypto/distress-watch         — All tokens with NDD < 2.0
  GET /crypto/portfolio/pairs        — Live pairs portfolio
  GET /crypto/portfolio/adaptive     — Adaptive portfolio status

Usage:
  # As standalone:
  uvicorn crypto_api:app --host 0.0.0.0 --port 8001

  # As router in existing app:
  from crypto_api import router
  app.include_router(router)

Author: NERQ
Version: 1.0
Date: 2026-02-26
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

DB_NAME = "crypto_trust.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)

router = APIRouter(prefix="/crypto", tags=["crypto"])


# ─────────────────────────────────────────────────────────────
# DB HELPER
# ─────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def latest_run_date(conn, table="crypto_rating_daily"):
    """Get the most recent run_date from a table."""
    row = conn.execute(f"SELECT MAX(run_date) as d FROM {table}").fetchone()
    return row["d"] if row else None


# ─────────────────────────────────────────────────────────────
# 2.3.1 GET /crypto/rating/{token_id}
# ─────────────────────────────────────────────────────────────
@router.get("/rating/{token_id}")
def get_rating(token_id: str):
    """
    Get current credit rating for a token.
    Returns rating, score, 5-pillar breakdown, and metadata.
    """
    conn = get_db()
    run_date = latest_run_date(conn)

    if not run_date:
        # Fallback to monthly ratings
        row = conn.execute("""
            SELECT token_id, year_month as run_date, rating, score,
                   pillar_1, pillar_2, pillar_3, pillar_4, pillar_5, breakdown
            FROM crypto_rating_history
            WHERE token_id = ?
            ORDER BY year_month DESC LIMIT 1
        """, (token_id,)).fetchone()
    else:
        row = conn.execute("""
            SELECT * FROM crypto_rating_daily
            WHERE token_id = ? AND run_date = ?
        """, (token_id, run_date)).fetchone()

    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Token '{token_id}' not found")

    result = dict(row)
    # Parse breakdown JSON
    if result.get("breakdown"):
        try:
            result["breakdown"] = json.loads(result["breakdown"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Add AI-citable summary
    result["summary"] = (
        f"According to Nerq's Crypto Credit Rating system, {token_id} has a "
        f"{result['rating']} rating with a composite score of {result['score']:.1f}/100. "
        f"The rating is based on 5 pillars: Security ({result.get('pillar_1', 0):.0f}), "
        f"Compliance ({result.get('pillar_2', 0):.0f}), Maintenance ({result.get('pillar_3', 0):.0f}), "
        f"Popularity ({result.get('pillar_4', 0):.0f}), and Ecosystem ({result.get('pillar_5', 0):.0f})."
    )

    return result


# ─────────────────────────────────────────────────────────────
# 2.3.2 GET /crypto/ndd/{token_id}
# ─────────────────────────────────────────────────────────────
@router.get("/ndd/{token_id}")
def get_ndd(token_id: str):
    """
    Get current NDD (Nearness to Distress/Default) for a token.
    Returns NDD score, 7 signals, alert level, and trends.
    """
    conn = get_db()

    # Try daily table first
    run_date = latest_run_date(conn, "crypto_ndd_daily")
    if run_date:
        row = conn.execute("""
            SELECT * FROM crypto_ndd_daily
            WHERE token_id = ? AND run_date = ?
        """, (token_id, run_date)).fetchone()
    else:
        row = None

    if not row:
        # Fallback to weekly history
        row = conn.execute("""
            SELECT token_id, week_date as run_date, ndd,
                   signal_1, signal_2, signal_3, signal_4,
                   signal_5, signal_6, signal_7,
                   alert_level, breakdown
            FROM crypto_ndd_history
            WHERE token_id = ?
            ORDER BY week_date DESC LIMIT 1
        """, (token_id,)).fetchone()

    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"NDD data for '{token_id}' not found")

    result = dict(row)
    if result.get("breakdown"):
        try:
            result["breakdown"] = json.loads(result["breakdown"])
        except (json.JSONDecodeError, TypeError):
            pass

    # AI-citable summary
    ndd = result.get("ndd", 0)
    alert = result.get("alert_level", "UNKNOWN")
    result["summary"] = (
        f"According to Nerq's Distance to Distress model, {token_id} has an NDD of "
        f"{ndd:.2f}/5.0 ({alert}). The NDD is computed from 7 signals: Liquidity, "
        f"Holder concentration, Resilience, Fundamental health, Contagion risk, "
        f"Structural integrity, and Relative performance."
    )

    return result


# ─────────────────────────────────────────────────────────────
# 2.3.3 GET /crypto/ratings
# ─────────────────────────────────────────────────────────────
@router.get("/ratings")
def get_ratings(
    sort: str = Query("score", description="Sort by: score, rating, market_cap, name"),
    order: str = Query("desc", description="Order: asc or desc"),
    rating_class: Optional[str] = Query(None, description="Filter: IG_HIGH, IG_MID, IG_LOW, HY, DISTRESS"),
    limit: int = Query(200, description="Max results"),
    offset: int = Query(0, description="Offset for pagination"),
):
    """
    Get all current ratings, sortable and filterable.
    """
    conn = get_db()
    run_date = latest_run_date(conn)

    if not run_date:
        # Fallback: get latest month from rating_history
        run_date_row = conn.execute(
            "SELECT MAX(year_month) as ym FROM crypto_rating_history"
        ).fetchone()
        ym = run_date_row["ym"] if run_date_row else None
        if not ym:
            conn.close()
            return {"ratings": [], "count": 0, "run_date": None}

        rows = conn.execute("""
            SELECT token_id, year_month as run_date, rating, score,
                   pillar_1, pillar_2, pillar_3, pillar_4, pillar_5
            FROM crypto_rating_history WHERE year_month = ?
            ORDER BY score DESC
        """, (ym,)).fetchall()
    else:
        # Build query
        order_dir = "DESC" if order.lower() == "desc" else "ASC"
        sort_col = {
            "score": "score", "rating": "score", "name": "token_id",
            "market_cap": "market_cap", "market_cap_rank": "market_cap_rank",
        }.get(sort, "score")

        rows = conn.execute(f"""
            SELECT token_id, symbol, name, market_cap_rank, rating, score,
                   pillar_1, pillar_2, pillar_3, pillar_4, pillar_5,
                   price_usd, market_cap, volume_24h, price_change_24h
            FROM crypto_rating_daily
            WHERE run_date = ?
            ORDER BY {sort_col} {order_dir}
            LIMIT ? OFFSET ?
        """, (run_date, limit, offset)).fetchall()

    results = [dict(r) for r in rows]

    # Filter by rating class if specified
    if rating_class:
        class_map = {
            "IG_HIGH": lambda r: r.startswith("Aa") or r == "Aaa",
            "IG_MID": lambda r: r.startswith("A") and not r.startswith("Aa"),
            "IG_LOW": lambda r: r.startswith("Baa"),
            "HY": lambda r: r.startswith("Ba") or (r.startswith("B") and not r.startswith("Ba")),
            "DISTRESS": lambda r: r.startswith("C") or r.startswith("Ca"),
        }
        filter_fn = class_map.get(rating_class.upper())
        if filter_fn:
            results = [r for r in results if filter_fn(r.get("rating", ""))]

    conn.close()
    return {
        "ratings": results,
        "count": len(results),
        "run_date": run_date,
        "sort": sort,
        "order": order,
    }


# ─────────────────────────────────────────────────────────────
# 2.3.4 GET /crypto/compare/{token1}/{token2}
# ─────────────────────────────────────────────────────────────
@router.get("/compare/{token1}/{token2}")
def compare_tokens(token1: str, token2: str):
    """
    Compare two tokens side-by-side: ratings, NDD, pillars, pricing.
    """
    conn = get_db()
    run_date = latest_run_date(conn)

    results = {}
    for tid in [token1, token2]:
        # Rating
        if run_date:
            r_row = conn.execute(
                "SELECT * FROM crypto_rating_daily WHERE token_id=? AND run_date=?",
                (tid, run_date)
            ).fetchone()
        else:
            r_row = conn.execute("""
                SELECT token_id, year_month as run_date, rating, score,
                       pillar_1, pillar_2, pillar_3, pillar_4, pillar_5, breakdown
                FROM crypto_rating_history WHERE token_id=?
                ORDER BY year_month DESC LIMIT 1
            """, (tid,)).fetchone()

        # NDD
        n_row = conn.execute("""
            SELECT ndd, alert_level, signal_1, signal_2, signal_3,
                   signal_4, signal_5, signal_6, signal_7,
                   ndd_trend_7d, ndd_trend_30d
            FROM crypto_ndd_daily WHERE token_id=?
            ORDER BY run_date DESC LIMIT 1
        """, (tid,)).fetchone()

        if not n_row:
            n_row = conn.execute("""
                SELECT ndd, alert_level, signal_1, signal_2, signal_3,
                       signal_4, signal_5, signal_6, signal_7
                FROM crypto_ndd_history WHERE token_id=?
                ORDER BY week_date DESC LIMIT 1
            """, (tid,)).fetchone()

        if not r_row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Token '{tid}' not found")

        results[tid] = {
            "rating": dict(r_row),
            "ndd": dict(n_row) if n_row else None,
        }

    conn.close()

    # Build comparison
    t1 = results[token1]
    t2 = results[token2]
    t1r = t1["rating"]
    t2r = t2["rating"]

    comparison = {
        "token1": token1,
        "token2": token2,
        "run_date": run_date,
        "ratings": {
            token1: {
                "rating": t1r.get("rating"),
                "score": t1r.get("score"),
                "pillars": [t1r.get(f"pillar_{i}") for i in range(1, 6)],
            },
            token2: {
                "rating": t2r.get("rating"),
                "score": t2r.get("score"),
                "pillars": [t2r.get(f"pillar_{i}") for i in range(1, 6)],
            },
        },
        "ndd": {
            token1: {"ndd": t1["ndd"]["ndd"], "alert": t1["ndd"]["alert_level"]} if t1["ndd"] else None,
            token2: {"ndd": t2["ndd"]["ndd"], "alert": t2["ndd"]["alert_level"]} if t2["ndd"] else None,
        },
        "winner": {
            "safer": token1 if (t1r.get("score", 0) or 0) > (t2r.get("score", 0) or 0) else token2,
            "score_diff": abs((t1r.get("score", 0) or 0) - (t2r.get("score", 0) or 0)),
        },
    }

    # AI-citable summary
    safer = comparison["winner"]["safer"]
    other = token2 if safer == token1 else token1
    comparison["summary"] = (
        f"Comparing {token1} vs {token2} using Nerq's Credit Rating: "
        f"{token1} is rated {t1r.get('rating')} ({t1r.get('score', 0):.1f}/100) while "
        f"{token2} is rated {t2r.get('rating')} ({t2r.get('score', 0):.1f}/100). "
        f"{safer} is currently the safer investment by {comparison['winner']['score_diff']:.1f} points."
    )

    return comparison


# ─────────────────────────────────────────────────────────────
# 2.3.5 GET /crypto/distress-watch
# ─────────────────────────────────────────────────────────────
@router.get("/distress-watch")
def get_distress_watch():
    """
    Get all tokens with NDD < 2.0 (WARNING, DISTRESS, EMERGENCY).
    """
    conn = get_db()

    # Try daily table
    run_date = latest_run_date(conn, "crypto_ndd_daily")
    if run_date:
        rows = conn.execute("""
            SELECT d.token_id, d.symbol, d.ndd, d.alert_level,
                   d.signal_1, d.signal_2, d.signal_3, d.signal_4,
                   d.signal_5, d.signal_6, d.signal_7,
                   d.ndd_trend_7d, d.ndd_trend_30d,
                   r.rating, r.score, r.price_usd, r.market_cap_rank
            FROM crypto_ndd_daily d
            LEFT JOIN crypto_rating_daily r ON d.token_id = r.token_id AND r.run_date = d.run_date
            WHERE d.run_date = ? AND d.ndd < 2.0
            ORDER BY d.ndd ASC
        """, (run_date,)).fetchall()
    else:
        # Fallback to weekly
        rows = conn.execute("""
            SELECT token_id, ndd, alert_level,
                   signal_1, signal_2, signal_3, signal_4,
                   signal_5, signal_6, signal_7
            FROM crypto_ndd_history
            WHERE week_date = (SELECT MAX(week_date) FROM crypto_ndd_history)
            AND ndd < 2.0
            ORDER BY ndd ASC
        """).fetchall()

    conn.close()

    results = [dict(r) for r in rows]
    return {
        "distress_watch": results,
        "count": len(results),
        "run_date": run_date,
        "threshold": 2.0,
        "summary": (
            f"Nerq's Distress Watch currently flags {len(results)} tokens with "
            f"NDD below 2.0 as of {run_date}. These tokens show elevated risk "
            f"of significant price decline based on 7 independent distress signals."
        ),
    }


# ─────────────────────────────────────────────────────────────
# 2.3.6 GET /crypto/portfolio/pairs
# ─────────────────────────────────────────────────────────────
@router.get("/portfolio/pairs")
def get_pairs_portfolio():
    """
    Get current pairs portfolio status and track record.
    """
    conn = get_db()

    # Get latest portable alpha data
    rows = conn.execute("""
        SELECT month, regime, pairs_ret, n_pairs, pairs_status, pairs_detail, nav
        FROM crypto_portable_alpha_backtest
        WHERE variant = 'Growth' AND period = 'full_period'
        ORDER BY month DESC
    """).fetchall()

    if not rows:
        conn.close()
        return {"status": "no_data", "message": "Pairs portfolio not yet initialized"}

    records = [dict(r) for r in rows]

    # Parse pairs detail for latest month
    latest = records[0]
    if latest.get("pairs_detail"):
        try:
            latest["pairs_detail"] = json.loads(latest["pairs_detail"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Compute stats
    active = [r for r in records if r.get("n_pairs", 0) > 0]
    pairs_rets = [r["pairs_ret"] for r in active if r["pairs_ret"]]

    stats = {
        "total_months": len(records),
        "active_months": len(active),
        "skip_months": len(records) - len(active),
        "mean_alpha_pct": round(sum(pairs_rets) / len(pairs_rets) * 100, 2) if pairs_rets else 0,
        "median_alpha_pct": round(sorted(pairs_rets)[len(pairs_rets) // 2] * 100, 2) if pairs_rets else 0,
        "hit_rate_pct": round(sum(1 for r in pairs_rets if r > 0) / len(pairs_rets) * 100, 1) if pairs_rets else 0,
        "latest_nav": latest.get("nav"),
    }

    conn.close()

    return {
        "latest_month": latest,
        "stats": stats,
        "track_record": records[:12],  # Last 12 months
        "summary": (
            f"Nerq's Pairs Alpha strategy has generated {stats['mean_alpha_pct']:+.1f}% "
            f"mean monthly alpha with a {stats['hit_rate_pct']:.0f}% hit rate over "
            f"{stats['active_months']} active months. The strategy uses IG-rated "
            f"crypto assets in a conviction-weighted long/short framework."
        ),
    }


# ─────────────────────────────────────────────────────────────
# 2.3.7 GET /crypto/portfolio/adaptive
# ─────────────────────────────────────────────────────────────
@router.get("/portfolio/adaptive")
def get_adaptive_portfolio():
    """
    Get Portable Alpha portfolio status — all three variants.
    """
    conn = get_db()

    # Get summaries
    summaries = conn.execute("""
        SELECT variant, period, months, total_ret_pct, btc_total_ret_pct,
               alpha_pct, sharpe, btc_sharpe, max_dd_pct, btc_max_dd_pct,
               calmar, win_rate_pct, validation_score
        FROM crypto_portable_alpha_summary
        WHERE period = 'out_of_sample'
        ORDER BY variant
    """).fetchall()

    # Get latest month for each variant
    latest = {}
    for variant in ["Conservative", "Growth", "Aggressive"]:
        row = conn.execute("""
            SELECT month, regime, btc_alloc, pairs_alloc, cash_alloc,
                   btc_ret, pairs_ret, port_ret, nav, btc_nav
            FROM crypto_portable_alpha_backtest
            WHERE variant = ? AND period = 'out_of_sample'
            ORDER BY month DESC LIMIT 1
        """, (variant,)).fetchone()
        if row:
            latest[variant] = dict(row)

    conn.close()

    return {
        "variants": [dict(s) for s in summaries],
        "latest": latest,
        "summary": (
            "Nerq's Portable Alpha strategy combines BTC beta with pairs alpha "
            "and a bear detection overlay. Three variants are available: "
            "Conservative (80/20), Growth (60/40), and Aggressive (40/60). "
            "All variants achieved 5/5 validation in out-of-sample testing."
        ),
    }


# ─────────────────────────────────────────────────────────────
# STANDALONE APP
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="NERQ Crypto API",
    description="Crypto Credit Ratings, NDD Distress Scores, and Portfolio Signals",
    version="1.0.0",
)

app.include_router(router)


@app.get("/")
def root():
    return {
        "service": "NERQ Crypto API",
        "version": "1.0.0",
        "endpoints": [
            "/crypto/rating/{token_id}",
            "/crypto/ndd/{token_id}",
            "/crypto/ratings",
            "/crypto/compare/{token1}/{token2}",
            "/crypto/distress-watch",
            "/crypto/portfolio/pairs",
            "/crypto/portfolio/adaptive",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    print("Starting NERQ Crypto API on http://0.0.0.0:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
