#!/usr/bin/env python3
"""
ZARQ TRANSITION MATRIX + EXIT SCORE — Sprint 3.2.3
=====================================================
Analyzes how token ratings change over time and calculates exit difficulty.

Features:
  1. Transition Matrix (30d/90d/365d) — probability of rating grade migration
  2. Liquidity Exit Score (0-100) — how easily can you exit a position
  3. Volatility-adjusted crash thresholds — personalized per token
  4. API-ready (returns dicts)

Usage:
  from transition_matrix import TransitionEngine
  te = TransitionEngine(db_path)
  matrix = te.get_transition_matrix(period="90d")
  exit_score = te.get_exit_score("solana")
  thresholds = te.get_crash_thresholds("bitcoin")

Author: ZARQ
Version: 1.0
Sprint: 3.2.3
"""

import sqlite3
import os
import json
import logging
from datetime import datetime, timedelta
from math import sqrt, log
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("zarq.transition")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")

# Rating grades ordered from best to worst (Moody's-style)
RATING_ORDER = [
    "Aaa", "Aa1", "Aa2", "Aa3",
    "A1", "A2", "A3",
    "Baa1", "Baa2", "Baa3",
    "Ba1", "Ba2", "Ba3",
    "B1", "B2", "B3",
    "Caa1", "Caa2", "Caa3",
    "Ca", "C", "D",
]

# Simplified grade buckets for the matrix
GRADE_BUCKETS = {
    "A+": ["Aaa", "Aa1", "Aa2", "Aa3"],
    "A":  ["A1", "A2", "A3"],
    "B+": ["Baa1", "Baa2", "Baa3"],
    "B":  ["Ba1", "Ba2", "Ba3"],
    "C+": ["B1", "B2", "B3"],
    "C":  ["Caa1", "Caa2", "Caa3"],
    "D":  ["Ca", "C", "D"],
}

def rating_to_bucket(rating: str) -> str:
    """Convert Moody's-style rating to simplified bucket."""
    for bucket, ratings in GRADE_BUCKETS.items():
        if rating in ratings:
            return bucket
    return "D"

def rating_to_numeric(rating: str) -> int:
    """Convert rating to numeric (0=best, 21=worst)."""
    try:
        return RATING_ORDER.index(rating)
    except ValueError:
        return 21


# ══════════════════════════════════════════════════════════════════════════════
# TRANSITION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TransitionEngine:
    """Rating transition and exit score analysis."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    # ──────────────────────────────────────────────────────────────────────
    # 1. TRANSITION MATRIX
    # ──────────────────────────────────────────────────────────────────────

    def get_transition_matrix(self, period: str = "90d") -> Dict[str, Any]:
        """
        Compute rating transition matrix for a given period.

        Args:
            period: "30d", "90d", or "365d"

        Returns:
            Transition probabilities between grade buckets.
        """
        days = {"30d": 30, "90d": 90, "365d": 365}.get(period, 90)

        conn = sqlite3.connect(self.db_path)

        # Get all available dates
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT run_date FROM crypto_rating_daily ORDER BY run_date"
        ).fetchall()]

        if len(dates) < 2:
            conn.close()
            return {"error": "Insufficient historical data for transition matrix"}

        # Find date pairs approximately 'days' apart
        transitions = defaultdict(lambda: defaultdict(int))
        n_transitions = 0

        for i, start_date in enumerate(dates):
            # Find closest date ~days later
            target = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=days)
            target_str = target.strftime("%Y-%m-%d")

            # Find closest available date
            end_date = None
            for d in dates[i+1:]:
                if d >= target_str:
                    end_date = d
                    break

            if not end_date:
                continue

            # Check that it's roughly the right period (within 20%)
            actual_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
            if actual_days < days * 0.7 or actual_days > days * 1.5:
                continue

            # Get ratings at start and end
            start_ratings = {}
            for r in conn.execute(
                "SELECT token_id, rating FROM crypto_rating_daily WHERE run_date = ?",
                (start_date,)
            ).fetchall():
                start_ratings[r[0]] = r[1]

            end_ratings = {}
            for r in conn.execute(
                "SELECT token_id, rating FROM crypto_rating_daily WHERE run_date = ?",
                (end_date,)
            ).fetchall():
                end_ratings[r[0]] = r[1]

            # Count transitions
            for token_id, start_r in start_ratings.items():
                if token_id in end_ratings:
                    from_bucket = rating_to_bucket(start_r)
                    to_bucket = rating_to_bucket(end_ratings[token_id])
                    transitions[from_bucket][to_bucket] += 1
                    n_transitions += 1

        conn.close()

        # Convert counts to probabilities
        buckets = list(GRADE_BUCKETS.keys())
        matrix = {}
        for from_b in buckets:
            row = transitions[from_b]
            total = sum(row.values())
            matrix[from_b] = {}
            for to_b in buckets:
                if total > 0:
                    matrix[from_b][to_b] = round(row[to_b] / total * 100, 1)
                else:
                    matrix[from_b][to_b] = 0.0

        # Compute summary stats
        upgrades = 0
        downgrades = 0
        stable = 0
        for from_b in buckets:
            from_idx = buckets.index(from_b)
            for to_b in buckets:
                to_idx = buckets.index(to_b)
                count = transitions[from_b][to_b]
                if to_idx < from_idx:
                    upgrades += count
                elif to_idx > from_idx:
                    downgrades += count
                else:
                    stable += count

        return {
            "period": period,
            "period_days": days,
            "matrix": matrix,
            "buckets": buckets,
            "summary": {
                "total_transitions": n_transitions,
                "upgrades": upgrades,
                "downgrades": downgrades,
                "stable": stable,
                "upgrade_rate_pct": round(upgrades / max(1, n_transitions) * 100, 1),
                "downgrade_rate_pct": round(downgrades / max(1, n_transitions) * 100, 1),
                "stability_rate_pct": round(stable / max(1, n_transitions) * 100, 1),
            },
            "interpretation": {
                "A+": f"{matrix.get('A+', {}).get('A+', 0):.0f}% of A+ rated tokens maintain their grade over {period}",
                "D": f"{matrix.get('D', {}).get('D', 0):.0f}% of D rated tokens remain D (recovery is rare)",
            },
            "generated_at": datetime.now().isoformat(),
        }

    def get_token_transition_history(self, token_id: str) -> Dict[str, Any]:
        """Get complete rating transition history for a specific token."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT run_date, rating, score FROM crypto_rating_daily
            WHERE token_id = ? ORDER BY run_date
        """, (token_id,)).fetchall()
        conn.close()

        if not rows:
            return {"error": f"No rating history for {token_id}"}

        history = [{"date": r["run_date"], "rating": r["rating"], "score": round(r["score"], 1)} for r in rows]

        # Count transitions
        transitions = []
        for i in range(1, len(history)):
            if history[i]["rating"] != history[i-1]["rating"]:
                transitions.append({
                    "date": history[i]["date"],
                    "from": history[i-1]["rating"],
                    "to": history[i]["rating"],
                    "direction": "upgrade" if rating_to_numeric(history[i]["rating"]) < rating_to_numeric(history[i-1]["rating"]) else "downgrade",
                })

        return {
            "token_id": token_id,
            "current_rating": history[-1]["rating"] if history else None,
            "current_score": history[-1]["score"] if history else None,
            "first_rating": history[0]["rating"] if history else None,
            "first_date": history[0]["date"] if history else None,
            "total_transitions": len(transitions),
            "upgrades": len([t for t in transitions if t["direction"] == "upgrade"]),
            "downgrades": len([t for t in transitions if t["direction"] == "downgrade"]),
            "transitions": transitions[-20:],  # Last 20
            "data_points": len(history),
        }

    # ──────────────────────────────────────────────────────────────────────
    # 2. LIQUIDITY EXIT SCORE
    # ──────────────────────────────────────────────────────────────────────

    def get_exit_score(self, token_id: str, position_usd: float = 100000) -> Dict[str, Any]:
        """
        Calculate how easily a position can be exited.

        Exit Score 0-100:
          90-100: Instant exit, minimal slippage
          70-89:  Easy exit, low slippage
          50-69:  Moderate difficulty
          30-49:  Difficult, significant slippage expected
          0-29:   Very difficult, may take days
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Get latest rating data
        max_date = conn.execute("SELECT MAX(run_date) FROM crypto_rating_daily").fetchone()[0]
        rating = conn.execute(
            "SELECT * FROM crypto_rating_daily WHERE run_date = ? AND token_id = ?",
            (max_date, token_id)
        ).fetchone()

        if not rating:
            conn.close()
            return {"error": f"Token '{token_id}' not found"}

        rating = dict(rating)

        # Enrich with NDD metadata if rating fields are empty
        max_ndd = conn.execute("SELECT MAX(run_date) FROM crypto_ndd_daily").fetchone()[0]
        if max_ndd:
            ndd_row = conn.execute(
                "SELECT symbol, name, market_cap, market_cap_rank, volume_24h FROM crypto_ndd_daily WHERE run_date = ? AND token_id = ?",
                (max_ndd, token_id)
            ).fetchone()
            if ndd_row:
                for col in ["symbol", "name", "market_cap", "market_cap_rank", "volume_24h"]:
                    if not rating.get(col):
                        rating[col] = ndd_row[col]

        # Get volume history (30 days)
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        vol_rows = conn.execute("""
            SELECT date, volume FROM crypto_price_history
            WHERE token_id = ? AND date >= ? AND volume > 0
            ORDER BY date
        """, (token_id, cutoff)).fetchall()
        conn.close()

        volumes = [r[1] for r in vol_rows]
        avg_volume = sum(volumes) / len(volumes) if volumes else 0
        min_volume = min(volumes) if volumes else 0
        vol_consistency = min(volumes) / max(volumes) if volumes and max(volumes) > 0 else 0

        # Calculate components
        volume_score = self._volume_exit_score(avg_volume, position_usd)
        mcap_score = self._mcap_exit_score(rating.get("market_cap") or 0)
        rank_score = self._rank_exit_score(rating.get("market_cap_rank") or 999)
        consistency_score = vol_consistency * 100

        # Weighted exit score
        exit_score = (
            volume_score * 0.40 +
            mcap_score * 0.25 +
            rank_score * 0.20 +
            consistency_score * 0.15
        )
        exit_score = round(min(100, max(0, exit_score)), 1)

        # Estimate slippage
        slippage_pct = self._estimate_slippage(position_usd, avg_volume)

        # Estimate exit time
        exit_time = self._estimate_exit_time(position_usd, avg_volume)

        return {
            "token_id": token_id,
            "symbol": rating.get("symbol"),
            "name": rating.get("name"),
            "exit_score": exit_score,
            "exit_difficulty": self._score_to_difficulty(exit_score),
            "position_usd": position_usd,
            "components": {
                "volume_score": round(volume_score, 1),
                "mcap_score": round(mcap_score, 1),
                "rank_score": round(rank_score, 1),
                "consistency_score": round(consistency_score, 1),
            },
            "liquidity_metrics": {
                "avg_daily_volume_usd": round(avg_volume, 0),
                "min_daily_volume_usd": round(min_volume, 0),
                "volume_consistency": round(vol_consistency, 2),
                "market_cap": rating.get("market_cap"),
                "volume_to_mcap_ratio": round(avg_volume / rating["market_cap"] * 100, 2) if rating.get("market_cap") and rating["market_cap"] > 0 else 0,
            },
            "exit_estimates": {
                "estimated_slippage_pct": round(slippage_pct, 2),
                "estimated_slippage_usd": round(position_usd * slippage_pct / 100, 2),
                "estimated_exit_hours": exit_time,
                "can_exit_in_one_trade": position_usd < avg_volume * 0.01,
            },
            "generated_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _volume_exit_score(avg_volume: float, position_usd: float) -> float:
        """Score based on volume relative to position size."""
        if avg_volume == 0:
            return 0
        ratio = avg_volume / max(1, position_usd)
        if ratio > 1000: return 100
        if ratio > 100: return 90
        if ratio > 10: return 75
        if ratio > 1: return 60
        if ratio > 0.1: return 35
        return 10

    @staticmethod
    def _mcap_exit_score(mcap: float) -> float:
        """Score based on market cap."""
        if mcap > 100e9: return 100
        if mcap > 10e9: return 90
        if mcap > 1e9: return 75
        if mcap > 100e6: return 55
        if mcap > 10e6: return 30
        return 10

    @staticmethod
    def _rank_exit_score(rank: int) -> float:
        """Score based on market cap rank."""
        if rank <= 10: return 100
        if rank <= 30: return 85
        if rank <= 50: return 70
        if rank <= 100: return 55
        if rank <= 200: return 35
        return 15

    @staticmethod
    def _estimate_slippage(position_usd: float, avg_volume: float) -> float:
        """Estimate slippage percentage."""
        if avg_volume == 0:
            return 10.0
        # Position as % of daily volume
        pct_of_volume = position_usd / avg_volume * 100
        # Square root market impact model
        slippage = 0.1 * sqrt(max(0, pct_of_volume))
        return min(10.0, slippage)

    @staticmethod
    def _estimate_exit_time(position_usd: float, avg_volume: float) -> float:
        """Estimate hours to exit position (targeting <1% of each hour's volume)."""
        if avg_volume == 0:
            return 999
        hourly_volume = avg_volume / 24
        target_per_hour = hourly_volume * 0.01  # 1% of hourly volume
        if target_per_hour == 0:
            return 999
        hours = position_usd / target_per_hour
        return round(min(999, hours), 1)

    @staticmethod
    def _score_to_difficulty(score: float) -> str:
        if score >= 90: return "INSTANT"
        if score >= 70: return "EASY"
        if score >= 50: return "MODERATE"
        if score >= 30: return "DIFFICULT"
        return "VERY_DIFFICULT"

    # ──────────────────────────────────────────────────────────────────────
    # 3. VOLATILITY-ADJUSTED CRASH THRESHOLDS
    # ──────────────────────────────────────────────────────────────────────

    def get_crash_thresholds(self, token_id: str) -> Dict[str, Any]:
        """
        Calculate personalized crash thresholds based on historical volatility.

        A -30% move for BTC is rare; for a small-cap meme coin, it's a normal week.
        This function defines what constitutes a "crash" for each token individually.
        """
        conn = sqlite3.connect(self.db_path)

        # Get price history (1 year)
        cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT date, close FROM crypto_price_history
            WHERE token_id = ? AND date >= ? AND close > 0
            ORDER BY date
        """, (token_id, cutoff)).fetchall()

        # Get rating info
        max_date = conn.execute("SELECT MAX(run_date) FROM crypto_rating_daily").fetchone()[0]
        rating_row = conn.execute(
            "SELECT symbol, name, rating, score FROM crypto_rating_daily WHERE run_date = ? AND token_id = ?",
            (max_date, token_id)
        ).fetchone()

        conn.close()

        if len(rows) < 30:
            return {"error": f"Insufficient price history for {token_id}"}

        prices = [r[1] for r in rows]
        dates = [r[0] for r in rows]

        # Calculate returns at different windows
        daily_returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        weekly_returns = [(prices[i] - prices[max(0,i-7)]) / prices[max(0,i-7)] for i in range(7, len(prices))]
        monthly_returns = [(prices[i] - prices[max(0,i-30)]) / prices[max(0,i-30)] for i in range(30, len(prices))]

        # Volatility metrics
        daily_vol = self._std(daily_returns) if daily_returns else 0
        weekly_vol = self._std(weekly_returns) if weekly_returns else 0
        monthly_vol = self._std(monthly_returns) if monthly_returns else 0

        # Max drawdown
        peak = prices[0]
        max_dd = 0
        for p in prices:
            peak = max(peak, p)
            dd = (p - peak) / peak
            max_dd = min(max_dd, dd)

        # Percentile-based thresholds
        sorted_daily = sorted(daily_returns)
        sorted_weekly = sorted(weekly_returns) if weekly_returns else [0]
        sorted_monthly = sorted(monthly_returns) if monthly_returns else [0]

        # Crash = worse than 1st percentile (historically extreme)
        # Correction = worse than 5th percentile
        # Dip = worse than 10th percentile
        def percentile(data, p):
            idx = max(0, int(len(data) * p / 100))
            return data[idx] if data else 0

        thresholds = {
            "daily": {
                "dip": round(percentile(sorted_daily, 10) * 100, 1),
                "correction": round(percentile(sorted_daily, 5) * 100, 1),
                "crash": round(percentile(sorted_daily, 1) * 100, 1),
            },
            "weekly": {
                "dip": round(percentile(sorted_weekly, 10) * 100, 1),
                "correction": round(percentile(sorted_weekly, 5) * 100, 1),
                "crash": round(percentile(sorted_weekly, 1) * 100, 1),
            },
            "monthly": {
                "dip": round(percentile(sorted_monthly, 10) * 100, 1),
                "correction": round(percentile(sorted_monthly, 5) * 100, 1),
                "crash": round(percentile(sorted_monthly, 1) * 100, 1),
            },
        }

        return {
            "token_id": token_id,
            "symbol": rating_row[0] if rating_row else token_id,
            "name": rating_row[1] if rating_row else token_id,
            "current_rating": rating_row[2] if rating_row else None,
            "thresholds": thresholds,
            "volatility": {
                "daily_vol_pct": round(daily_vol * 100, 2),
                "weekly_vol_pct": round(weekly_vol * 100, 2),
                "monthly_vol_pct": round(monthly_vol * 100, 2),
                "annualized_vol_pct": round(daily_vol * sqrt(365) * 100, 1),
                "max_drawdown_pct": round(max_dd * 100, 1),
            },
            "context": {
                "data_points": len(prices),
                "period_start": dates[0],
                "period_end": dates[-1],
                "current_price": prices[-1],
                "period_high": max(prices),
                "period_low": min(prices),
                "current_drawdown_from_high_pct": round((prices[-1] - max(prices)) / max(prices) * 100, 1),
            },
            "interpretation": self._interpret_thresholds(token_id, thresholds, daily_vol),
            "generated_at": datetime.now().isoformat(),
        }

    def _interpret_thresholds(self, token_id: str, thresholds: Dict, daily_vol: float) -> Dict:
        """Human-readable interpretation of crash thresholds."""
        monthly_crash = thresholds["monthly"]["crash"]
        is_volatile = daily_vol > 0.05

        return {
            "volatility_class": "HIGH" if daily_vol > 0.05 else "MODERATE" if daily_vol > 0.03 else "LOW",
            "monthly_crash_threshold": f"A move of {monthly_crash:.0f}% in a month would be a historically extreme crash for this token",
            "note": (
                f"This token is {'highly volatile' if is_volatile else 'moderately volatile'}. "
                f"A -30% monthly move {'is within normal range' if monthly_crash < -30 else 'would be unusual'}."
            ),
        }

    @staticmethod
    def _std(data):
        if len(data) < 2:
            return 0
        m = sum(data) / len(data)
        return sqrt(sum((x - m) ** 2 for x in data) / (len(data) - 1))


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ZARQ Transition Matrix + Exit Score")
    parser.add_argument("--matrix", type=str, help="Transition matrix period (30d, 90d, 365d)")
    parser.add_argument("--exit-score", type=str, help="Exit score for token_id")
    parser.add_argument("--crash-thresholds", type=str, help="Crash thresholds for token_id")
    parser.add_argument("--token-history", type=str, help="Rating transition history for token_id")
    parser.add_argument("--position", type=float, default=100000, help="Position size in USD")
    parser.add_argument("--db", type=str, default=DB_PATH)
    args = parser.parse_args()

    te = TransitionEngine(args.db)

    if args.matrix:
        result = te.get_transition_matrix(args.matrix)
        print(json.dumps(result, indent=2))
    elif args.exit_score:
        result = te.get_exit_score(args.exit_score, args.position)
        print(json.dumps(result, indent=2))
    elif args.crash_thresholds:
        result = te.get_crash_thresholds(args.crash_thresholds)
        print(json.dumps(result, indent=2))
    elif args.token_history:
        result = te.get_token_transition_history(args.token_history)
        print(json.dumps(result, indent=2))
    else:
        # Default: show all
        print("=== 90-day Transition Matrix ===")
        m = te.get_transition_matrix("90d")
        print(json.dumps(m["summary"], indent=2))
        print("\n=== Exit Scores (BTC, ETH, SOL) ===")
        for tid in ["bitcoin", "ethereum", "solana"]:
            es = te.get_exit_score(tid)
            print(f"  {es.get('symbol', tid):>5}: Exit Score {es.get('exit_score', 0):>5.1f} ({es.get('exit_difficulty', '?')})")
        print("\n=== Crash Thresholds (BTC, ETH, SOL) ===")
        for tid in ["bitcoin", "ethereum", "solana"]:
            ct = te.get_crash_thresholds(tid)
            if "thresholds" in ct:
                t = ct["thresholds"]["monthly"]
                print(f"  {ct.get('symbol', tid):>5}: Dip {t['dip']:>+6.1f}% | Correction {t['correction']:>+6.1f}% | Crash {t['crash']:>+6.1f}%")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
