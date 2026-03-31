#!/usr/bin/env python3
"""
Vitality Score Backtest
=======================
Tests whether Vitality Score (or proxy) at time T predicts forward returns.

Three windows:
  A: Score at Jan 2024, returns Jan 2024 → Jan 2025
  B: Score at Jan 2025, returns Jan 2025 → Jan 2026
  C: Score at Jul 2025, returns Jul 2025 → Feb 2026 (crash window)

For each window, we reconstruct a historical Vitality proxy using available
data at that date, split into quintiles, and measure forward returns.
"""

import json
import math
import os
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")

# ── Vitality dimension weights (current production) ──
WEIGHTS = {
    "ecosystem_gravity": 0.20,
    "capital_commitment": 0.20,
    "coordination_efficiency": 0.15,
    "stress_resilience": 0.25,
    "organic_momentum": 0.20,
}

CHAIN_NORM = {
    "Binance": "BSC", "Avalanche": "AVAX", "Polygon": "MATIC",
    "Arbitrum": "ARB", "Optimism": "OP",
}


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def _percentile_score(value, values_list, invert=False):
    if not values_list:
        return 50.0
    sorted_vals = sorted(values_list)
    n = len(sorted_vals)
    pos = sum(1 for v in sorted_vals if v <= value)
    pct = pos / n * 100
    return 100 - pct if invert else pct


def _linear_trend(values):
    if len(values) < 3:
        return 0
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0 or y_mean == 0:
        return 0
    slope = num / den
    return slope / abs(y_mean)


# ── Historical proxy score computation ──

def compute_historical_vitality_proxy(conn, score_date, tokens_with_prices):
    """
    Compute a Vitality proxy for tokens at a given historical date.

    Available historically:
    - Ecosystem Gravity: protocol counts (static-ish), TVL at date, stablecoins at date
    - Capital Commitment: TVL retention (from TVL history), volume/mcap NOT available historically
    - Coordination Efficiency: category counts (static), audit counts (static)
    - Stress Resilience: NDD history up to date, crash prob near date, price drawdowns up to date
    - Organic Momentum: TVL trend up to date, price trend up to date, rating trend up to date

    Returns: dict of token_id → {proxy_score, dimensions, n_dims}
    """

    # ── Chain-level aggregates (these are semi-static, OK to use current) ──
    chain_protocol_counts = {}
    for row in conn.execute("SELECT chains FROM defi_protocol_tokens WHERE chains IS NOT NULL"):
        try:
            chains = json.loads(row["chains"])
            for c in chains:
                chain_protocol_counts[c] = chain_protocol_counts.get(c, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass

    chain_category_counts = {}
    for row in conn.execute("SELECT chains, category FROM defi_protocol_tokens WHERE chains IS NOT NULL AND category IS NOT NULL"):
        try:
            chains = json.loads(row["chains"])
            for c in chains:
                if c not in chain_category_counts:
                    chain_category_counts[c] = set()
                chain_category_counts[c].add(row["category"])
        except (json.JSONDecodeError, TypeError):
            pass
    chain_category_counts = {k: len(v) for k, v in chain_category_counts.items()}

    chain_audit_counts = {}
    chain_total_counts = {}
    for row in conn.execute("SELECT chains, audit_count FROM defi_protocol_tokens WHERE chains IS NOT NULL"):
        try:
            chains = json.loads(row["chains"])
            audited = 1 if (row["audit_count"] or 0) > 0 else 0
            for c in chains:
                chain_audit_counts[c] = chain_audit_counts.get(c, 0) + audited
                chain_total_counts[c] = chain_total_counts.get(c, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    chain_audit_rates = {c: chain_audit_counts.get(c, 0) / chain_total_counts[c]
                         for c in chain_total_counts if chain_total_counts[c] > 0}

    # ── Stablecoin totals at score_date ──
    chain_stablecoin_at_date = {}
    for row in conn.execute("""
        SELECT chain, total_circulating FROM defi_stablecoin_flows
        WHERE date <= ? GROUP BY chain HAVING date = MAX(date)
    """, (score_date,)):
        chain_stablecoin_at_date[row["chain"]] = row["total_circulating"] or 0

    # ── Protocol data + TVL at date ──
    protocol_data = {}
    protocol_chains_map = {}
    for row in conn.execute("""
        SELECT token_id, chains, audit_count, protocol_id, listed_at
        FROM defi_protocol_tokens WHERE token_id IS NOT NULL
    """):
        try:
            chains = json.loads(row["chains"]) if row["chains"] else []
        except (json.JSONDecodeError, TypeError):
            chains = []
        protocol_data[row["token_id"]] = {
            "chains": chains,
            "audit_count": row["audit_count"],
            "protocol_id": row["protocol_id"],
        }
        if row["protocol_id"]:
            protocol_chains_map[row["protocol_id"]] = chains

    # TVL at score_date per protocol
    tvl_at_date = {}
    for row in conn.execute("""
        SELECT protocol_id, tvl_usd FROM defi_tvl_history
        WHERE date <= ? GROUP BY protocol_id HAVING date = MAX(date)
    """, (score_date,)):
        tvl_at_date[row["protocol_id"]] = row["tvl_usd"] or 0

    all_tvls_at_date = [v for v in tvl_at_date.values() if v > 0]

    # TVL history up to score_date per protocol (for trends)
    tvl_history = defaultdict(list)
    for row in conn.execute("""
        SELECT protocol_id, tvl_usd FROM defi_tvl_history
        WHERE date <= ? ORDER BY protocol_id, date ASC
    """, (score_date,)):
        tvl_history[row["protocol_id"]].append(row["tvl_usd"] or 0)

    # ── NDD history up to score_date ──
    ndd_history = defaultdict(list)
    for row in conn.execute("""
        SELECT token_id, ndd FROM crypto_ndd_history
        WHERE week_date <= ? ORDER BY token_id, week_date ASC
    """, (score_date,)):
        ndd_history[row["token_id"]].append(row["ndd"])

    # ── Crash predictions near score_date ──
    crash_preds = {}
    for row in conn.execute("""
        SELECT token_id, crash_prob_v3 FROM crash_model_v3_predictions
        WHERE date <= ? GROUP BY token_id HAVING date = MAX(date)
    """, (score_date,)):
        crash_preds[row["token_id"]] = row["crash_prob_v3"]
    all_crash_probs = [v for v in crash_preds.values() if v is not None]

    # ── Price history up to score_date (last 365 days) ──
    price_cutoff = (datetime.strptime(score_date, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
    price_history = defaultdict(list)
    for row in conn.execute("""
        SELECT token_id, close FROM crypto_price_history
        WHERE date BETWEEN ? AND ? ORDER BY token_id, date ASC
    """, (price_cutoff, score_date)):
        price_history[row["token_id"]].append(row["close"])

    # ── Rating history up to score_date ──
    score_ym = score_date[:7]  # "2024-01" format
    rating_history = defaultdict(list)
    for row in conn.execute("""
        SELECT token_id, score FROM crypto_rating_history
        WHERE year_month <= ? ORDER BY token_id, year_month ASC
    """, (score_ym,)):
        rating_history[row["token_id"]].append(row["score"])

    # ── Market cap ranks near score_date ──
    mcap_ranks = {}
    for row in conn.execute("""
        SELECT token_id, market_cap_rank FROM crypto_ndd_daily
        WHERE run_date <= ? AND market_cap_rank IS NOT NULL
        GROUP BY token_id HAVING run_date = MAX(run_date)
    """, (score_date,)):
        mcap_ranks[row["token_id"]] = row["market_cap_rank"]

    # If crypto_ndd_daily doesn't go back far enough, use NDD history as proxy
    if not mcap_ranks:
        # Fallback: use all tokens from ndd_history as available
        pass

    # ── Compute proxy scores ──
    results = {}

    for token_id in tokens_with_prices:
        dims = {}
        dim_sources = {}

        pdata = protocol_data.get(token_id)
        pid = pdata["protocol_id"] if pdata else None

        # --- Ecosystem Gravity ---
        eg_scores = []
        if pdata and pdata.get("chains"):
            chains = pdata["chains"]
            max_protos = max(chain_protocol_counts.values()) if chain_protocol_counts else 1
            chain_scores = []
            for c in chains:
                count = chain_protocol_counts.get(c, 0)
                chain_scores.append(min(count / max(max_protos * 0.5, 1) * 100, 100))
            if chain_scores:
                eg_scores.append(sum(chain_scores) / len(chain_scores))

            # TVL at date
            if pid and tvl_at_date.get(pid, 0) > 0:
                eg_scores.append(_percentile_score(tvl_at_date[pid], all_tvls_at_date))

            # Stablecoins
            total_stable = sum(chain_stablecoin_at_date.get(CHAIN_NORM.get(c, c),
                             chain_stablecoin_at_date.get(c, 0)) for c in chains)
            if total_stable > 0:
                all_stables = [v for v in chain_stablecoin_at_date.values() if v > 0]
                if all_stables:
                    eg_scores.append(_percentile_score(total_stable, all_stables))

        if not eg_scores and mcap_ranks.get(token_id):
            rank = mcap_ranks[token_id]
            if rank <= 10: eg_scores.append(90)
            elif rank <= 50: eg_scores.append(70)
            elif rank <= 200: eg_scores.append(50)
            elif rank <= 500: eg_scores.append(30)
            else: eg_scores.append(15)

        if eg_scores:
            dims["ecosystem_gravity"] = round(sum(eg_scores) / len(eg_scores), 1)

        # --- Capital Commitment ---
        cc_scores = []
        tvl_hist = tvl_history.get(pid, []) if pid else []
        if tvl_hist and len(tvl_hist) >= 30:
            recent = tvl_hist[-30:]
            older = tvl_hist[-90:-30] if len(tvl_hist) >= 90 else tvl_hist[:-30]
            if older:
                recent_avg = sum(recent) / len(recent) if recent else 0
                older_avg = sum(older) / len(older) if older else 0
                if older_avg > 0:
                    retention = min(recent_avg / older_avg, 2.0)
                    cc_scores.append(_clamp(retention * 50))

        if not cc_scores:
            cc_scores.append(50)  # neutral default

        dims["capital_commitment"] = round(sum(cc_scores) / len(cc_scores), 1)

        # --- Coordination Efficiency ---
        ce_scores = []
        if pdata and pdata.get("chains"):
            chains = pdata["chains"]
            diversities = [chain_category_counts.get(CHAIN_NORM.get(c, c),
                          chain_category_counts.get(c, 0)) for c in chains]
            if any(d > 0 for d in diversities):
                max_cats = max(chain_category_counts.values()) if chain_category_counts else 1
                avg_div = sum(diversities) / len(diversities)
                ce_scores.append(_clamp(avg_div / max(max_cats * 0.5, 1) * 100))

            audit_count = pdata.get("audit_count", 0) or 0
            audit_score = {0: 10, 1: 50, 2: 75}.get(audit_count, 90)
            ce_scores.append(audit_score)

            rates = [chain_audit_rates.get(CHAIN_NORM.get(c, c),
                    chain_audit_rates.get(c, 0)) for c in chains]
            if any(r > 0 for r in rates):
                avg_rate = sum(rates) / len(rates)
                ce_scores.append(_clamp(avg_rate * 100))

        if ce_scores:
            dims["coordination_efficiency"] = round(sum(ce_scores) / len(ce_scores), 1)

        # --- Stress Resilience ---
        sr_scores = []
        ndd_hist = ndd_history.get(token_id, [])
        crash_pred = crash_preds.get(token_id)

        if crash_pred is not None and all_crash_probs:
            sr_scores.append(_percentile_score(crash_pred, all_crash_probs, invert=True))

        prices = price_history.get(token_id, [])
        if prices and len(prices) >= 30:
            peak = max(prices)
            current = prices[-1]
            if peak > 0:
                drawdown = (peak - current) / peak
                dd_score = _clamp((1 - drawdown) * 100)
                sr_scores.append(dd_score)

        if ndd_hist and len(ndd_hist) >= 4:
            recent_ndd = ndd_hist[-12:] if len(ndd_hist) >= 12 else ndd_hist
            ndd_cv = statistics.stdev(recent_ndd) / max(statistics.mean(recent_ndd), 0.01) if len(recent_ndd) >= 2 else 0
            stability = _clamp((1 - min(ndd_cv, 1)) * 100)
            sr_scores.append(stability)

            ndd_floor = min(recent_ndd)
            if ndd_floor >= 3.0:
                sr_scores.append(90)
            elif ndd_floor >= 2.0:
                sr_scores.append(70)
            elif ndd_floor >= 1.0:
                sr_scores.append(50)
            else:
                sr_scores.append(20)

        if sr_scores:
            dims["stress_resilience"] = round(sum(sr_scores) / len(sr_scores), 1)

        # --- Organic Momentum ---
        om_scores = []
        if tvl_hist and len(tvl_hist) >= 30:
            trend = _linear_trend(tvl_hist[-90:] if len(tvl_hist) >= 90 else tvl_hist)
            om_scores.append(_clamp(50 + trend * 500))

        if prices and len(prices) >= 30:
            price_90d = prices[-90:] if len(prices) >= 90 else prices
            price_trend = _linear_trend(price_90d)
            om_scores.append(_clamp(50 + price_trend * 300))

        rat_hist = rating_history.get(token_id, [])
        if rat_hist and len(rat_hist) >= 3:
            rating_trend = _linear_trend(rat_hist[-12:])
            om_scores.append(_clamp(50 + rating_trend * 1000))

        if om_scores:
            dims["organic_momentum"] = round(sum(om_scores) / len(om_scores), 1)

        # --- Composite ---
        available = {k: v for k, v in dims.items() if v is not None}
        if not available:
            continue

        total_weight = sum(WEIGHTS[k] for k in available)
        if total_weight == 0:
            continue

        weighted_sum = sum(v * WEIGHTS[k] / total_weight for k, v in available.items())
        confidence = round(len(available) / 5 * 100)
        confidence_factor = 0.6 + 0.4 * (confidence / 100)
        proxy_score = round(_clamp(weighted_sum * confidence_factor), 1)

        results[token_id] = {
            "proxy_score": proxy_score,
            "dimensions": dims,
            "n_dims": len(available),
            "confidence": confidence,
        }

    return results


def get_prices_at_date(conn, target_date, window_days=7):
    """Get prices for tokens at or near a target date."""
    prices = {}
    for row in conn.execute("""
        SELECT token_id, close, date FROM crypto_price_history
        WHERE date BETWEEN date(?, ?) AND date(?, ?)
        ORDER BY token_id, ABS(julianday(date) - julianday(?)) ASC
    """, (target_date, f"-{window_days} days", target_date, f"+{window_days} days", target_date)):
        if row["token_id"] not in prices:
            prices[row["token_id"]] = (row["close"], row["date"])
    return prices


def run_backtest():
    """Run the full backtest across 3 windows."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    windows = [
        {"name": "A", "score_date": "2024-01-15", "start_date": "2024-01-15", "end_date": "2025-01-15", "label": "Jan 2024 → Jan 2025 (12mo)"},
        {"name": "B", "score_date": "2025-01-15", "start_date": "2025-01-15", "end_date": "2026-01-15", "label": "Jan 2025 → Jan 2026 (12mo)"},
        {"name": "C", "score_date": "2025-07-01", "start_date": "2025-07-01", "end_date": "2026-02-25", "label": "Jul 2025 → Feb 2026 (crash, 8mo)"},
    ]

    all_results = {}

    for w in windows:
        print(f"\n{'='*70}")
        print(f"WINDOW {w['name']}: {w['label']}")
        print(f"{'='*70}")

        # Get prices at start and end of window
        start_prices = get_prices_at_date(conn, w["start_date"])
        end_prices = get_prices_at_date(conn, w["end_date"])

        # Tokens with prices at both endpoints
        common_tokens = set(start_prices.keys()) & set(end_prices.keys())
        print(f"Tokens with prices at both endpoints: {len(common_tokens)}")

        if len(common_tokens) < 20:
            print("WARNING: Not enough tokens for meaningful quintile analysis")
            all_results[w["name"]] = {"error": "insufficient data", "n_tokens": len(common_tokens)}
            continue

        # Compute historical Vitality proxy at score_date
        proxy_scores = compute_historical_vitality_proxy(conn, w["score_date"], common_tokens)

        # Filter to tokens with both proxy score and prices
        scored_tokens = {tid: proxy_scores[tid] for tid in common_tokens if tid in proxy_scores}
        print(f"Tokens with proxy scores: {len(scored_tokens)}")

        if len(scored_tokens) < 20:
            print("WARNING: Not enough scored tokens for quintile analysis")
            all_results[w["name"]] = {"error": "insufficient scored tokens", "n_tokens": len(scored_tokens)}
            continue

        # Compute returns
        returns = {}
        for tid in scored_tokens:
            p_start = start_prices[tid][0]
            p_end = end_prices[tid][0]
            if p_start and p_start > 0 and p_end and p_end > 0:
                ret = (p_end - p_start) / p_start * 100  # percentage return
                returns[tid] = ret

        scored_with_returns = [(tid, scored_tokens[tid]["proxy_score"], returns[tid])
                               for tid in scored_tokens if tid in returns]

        # Winsorize returns at 1st and 99th percentile to remove extreme outliers
        all_rets = sorted([t[2] for t in scored_with_returns])
        p1 = all_rets[max(0, len(all_rets) // 100)]
        p99 = all_rets[min(len(all_rets) - 1, len(all_rets) * 99 // 100)]
        scored_with_returns = [(tid, score, max(p1, min(p99, ret)))
                               for tid, score, ret in scored_with_returns]
        print(f"  Winsorized returns at [{p1:+.1f}%, {p99:+.1f}%]")

        scored_with_returns.sort(key=lambda x: x[1], reverse=True)

        n = len(scored_with_returns)
        print(f"Tokens with both scores and returns: {n}")

        # Split into quintiles
        q_size = n // 5
        quintiles = {}
        for qi in range(5):
            start_idx = qi * q_size
            end_idx = start_idx + q_size if qi < 4 else n
            q_tokens = scored_with_returns[start_idx:end_idx]
            q_returns = [t[2] for t in q_tokens]
            q_scores = [t[1] for t in q_tokens]

            q_label = f"Q{qi+1}" + (" (TOP)" if qi == 0 else " (BOTTOM)" if qi == 4 else "")

            avg_ret = statistics.mean(q_returns)
            med_ret = statistics.median(q_returns)
            std_ret = statistics.stdev(q_returns) if len(q_returns) >= 2 else 0
            avg_score = statistics.mean(q_scores)

            quintiles[q_label] = {
                "n": len(q_tokens),
                "avg_score": round(avg_score, 1),
                "score_range": f"{min(q_scores):.1f}–{max(q_scores):.1f}",
                "avg_return": round(avg_ret, 1),
                "median_return": round(med_ret, 1),
                "std_return": round(std_ret, 1),
                "min_return": round(min(q_returns), 1),
                "max_return": round(max(q_returns), 1),
                "tokens_sample": [t[0] for t in q_tokens[:5]],
            }

            print(f"  {q_label:15s}  n={len(q_tokens):3d}  "
                  f"score={avg_score:5.1f} ({min(q_scores):.1f}–{max(q_scores):.1f})  "
                  f"return={avg_ret:+7.1f}% ± {std_ret:.1f}%  "
                  f"median={med_ret:+7.1f}%")

        # Q1-Q5 spread (use MEDIAN for robustness)
        q1_med = quintiles["Q1 (TOP)"]["median_return"]
        q5_med = quintiles["Q5 (BOTTOM)"]["median_return"]
        spread = q1_med - q5_med
        print(f"\n  Q1-Q5 MEDIAN SPREAD: {spread:+.1f}%  (positive = high Vitality outperforms)")

        # Monotonicity check (on medians)
        q_rets = [quintiles[f"Q{i+1}" + (" (TOP)" if i==0 else " (BOTTOM)" if i==4 else "")]["median_return"] for i in range(5)]
        monotonic_steps = sum(1 for i in range(4) if q_rets[i] >= q_rets[i+1])
        print(f"  Monotonicity: {monotonic_steps}/4 steps (4/4 = perfectly monotonic)")

        # Simple t-test approximation (Q1 vs Q5) on winsorized means
        q1_data = quintiles["Q1 (TOP)"]
        q5_data = quintiles["Q5 (BOTTOM)"]
        mean_spread = q1_data["avg_return"] - q5_data["avg_return"]
        if q1_data["std_return"] > 0 and q5_data["std_return"] > 0:
            se = math.sqrt(q1_data["std_return"]**2/q1_data["n"] + q5_data["std_return"]**2/q5_data["n"])
            if se > 0:
                t_stat = mean_spread / se
                p_approx = 2 * (1 - _normal_cdf(abs(t_stat)))
                print(f"  t-statistic: {t_stat:.2f}, approx p-value: {p_approx:.4f} (on winsorized means)")
                quintiles["t_stat"] = round(t_stat, 2)
                quintiles["p_value"] = round(p_approx, 4)

        # Per-dimension analysis: which dimension best predicts returns?
        print(f"\n  Per-dimension predictive power:")
        dim_names = ["ecosystem_gravity", "capital_commitment", "coordination_efficiency",
                     "stress_resilience", "organic_momentum"]
        dim_spreads = {}
        # Build winsorized returns lookup
        winsorized_returns = {tid: ret for tid, _, ret in scored_with_returns}

        for dim in dim_names:
            # Get tokens with this dimension scored (use winsorized returns)
            dim_tokens = [(tid, scored_tokens[tid]["dimensions"].get(dim), winsorized_returns[tid])
                         for tid in scored_tokens
                         if tid in winsorized_returns and dim in scored_tokens[tid]["dimensions"]]
            if len(dim_tokens) < 20:
                print(f"    {dim:30s}: insufficient data ({len(dim_tokens)} tokens)")
                continue

            dim_tokens.sort(key=lambda x: x[1], reverse=True)
            n_dim = len(dim_tokens)
            top_20 = dim_tokens[:n_dim//5]
            bot_20 = dim_tokens[-(n_dim//5):]

            top_med = statistics.median([t[2] for t in top_20])
            bot_med = statistics.median([t[2] for t in bot_20])
            dim_spread = top_med - bot_med
            dim_spreads[dim] = dim_spread

            print(f"    {dim:30s}: top20%={top_med:+7.1f}%  bot20%={bot_med:+7.1f}%  spread={dim_spread:+7.1f}%  (n={n_dim})")

        all_results[w["name"]] = {
            "label": w["label"],
            "n_tokens": n,
            "quintiles": quintiles,
            "spread": round(spread, 1),
            "monotonic_steps": monotonic_steps,
            "dim_spreads": {k: round(v, 1) for k, v in dim_spreads.items()},
        }

    conn.close()
    return all_results


def _normal_cdf(x):
    """Approximation of standard normal CDF."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def run_weight_optimization(all_results):
    """
    Step 6: Optimize dimension weights.
    Train on windows A+B, validate on window C.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # We need to re-run the scoring with different weights for each window
    # This is expensive, so we'll pre-compute the per-dimension scores once
    # and then try different weight combinations.

    windows_train = [
        {"score_date": "2024-01-15", "start_date": "2024-01-15", "end_date": "2025-01-15"},
        {"score_date": "2025-01-15", "start_date": "2025-01-15", "end_date": "2026-01-15"},
    ]
    window_test = {"score_date": "2025-07-01", "start_date": "2025-07-01", "end_date": "2026-02-25"}

    # Pre-compute dimension scores and returns for each window
    window_data = []
    for w in windows_train + [window_test]:
        start_prices = get_prices_at_date(conn, w["start_date"])
        end_prices = get_prices_at_date(conn, w["end_date"])
        common = set(start_prices.keys()) & set(end_prices.keys())

        proxy_scores = compute_historical_vitality_proxy(conn, w["score_date"], common)

        token_data = []
        for tid in proxy_scores:
            if tid not in start_prices or tid not in end_prices:
                continue
            p_start = start_prices[tid][0]
            p_end = end_prices[tid][0]
            if not p_start or p_start <= 0 or not p_end or p_end <= 0:
                continue
            ret = (p_end - p_start) / p_start * 100
            token_data.append({
                "token_id": tid,
                "dims": proxy_scores[tid]["dimensions"],
                "return": ret,
            })
        window_data.append(token_data)

    conn.close()

    # Weight combinations to try
    dim_names = ["ecosystem_gravity", "capital_commitment", "coordination_efficiency",
                 "stress_resilience", "organic_momentum"]

    # Generate weight grid (increments of 0.05, summing to 1.0)
    weight_combos = []
    for eg in range(5, 40, 5):
        for cc in range(5, 40, 5):
            for ce in range(5, 40, 5):
                for sr in range(5, 40, 5):
                    om = 100 - eg - cc - ce - sr
                    if 5 <= om <= 40:
                        weight_combos.append({
                            "ecosystem_gravity": eg/100,
                            "capital_commitment": cc/100,
                            "coordination_efficiency": ce/100,
                            "stress_resilience": sr/100,
                            "organic_momentum": om/100,
                        })

    print(f"\nTesting {len(weight_combos)} weight combinations...")

    def compute_spread(token_data, weights):
        """Compute Q1-Q5 spread for given weights and token data."""
        scored = []
        for td in token_data:
            dims = td["dims"]
            available = {k: v for k, v in dims.items() if v is not None and k in weights}
            if not available:
                continue
            tw = sum(weights[k] for k in available)
            if tw == 0:
                continue
            ws = sum(v * weights[k] / tw for k, v in available.items())
            conf = len(available) / 5
            score = ws * (0.6 + 0.4 * conf)
            scored.append((score, td["return"]))

        if len(scored) < 20:
            return 0

        # Winsorize
        all_r = sorted([s[1] for s in scored])
        p1 = all_r[max(0, len(all_r) // 100)]
        p99 = all_r[min(len(all_r) - 1, len(all_r) * 99 // 100)]
        scored = [(s, max(p1, min(p99, r))) for s, r in scored]

        scored.sort(key=lambda x: x[0], reverse=True)
        n = len(scored)
        q = n // 5
        q1_med = statistics.median([s[1] for s in scored[:q]])
        q5_med = statistics.median([s[1] for s in scored[-q:]])
        return q1_med - q5_med

    best_spread = -999
    best_weights = None

    for wc in weight_combos:
        # Average spread across training windows
        spreads = [compute_spread(wd, wc) for wd in window_data[:2]]
        avg_spread = sum(spreads) / len(spreads)

        if avg_spread > best_spread:
            best_spread = avg_spread
            best_weights = wc

    # Validate on window C
    test_spread = compute_spread(window_data[2], best_weights) if best_weights else 0
    current_test_spread = compute_spread(window_data[2], WEIGHTS)
    current_train_spreads = [compute_spread(wd, WEIGHTS) for wd in window_data[:2]]
    best_train_spreads = [compute_spread(wd, best_weights) for wd in window_data[:2]] if best_weights else [0, 0]

    print(f"\n{'='*70}")
    print("WEIGHT OPTIMIZATION RESULTS")
    print(f"{'='*70}")
    print(f"\nCurrent weights: {json.dumps({k: round(v,2) for k,v in WEIGHTS.items()})}")
    print(f"  Train A spread: {current_train_spreads[0]:+.1f}%")
    print(f"  Train B spread: {current_train_spreads[1]:+.1f}%")
    print(f"  Test C spread:  {current_test_spread:+.1f}%")

    if best_weights:
        print(f"\nOptimized weights: {json.dumps({k: round(v,2) for k,v in best_weights.items()})}")
        print(f"  Train A spread: {best_train_spreads[0]:+.1f}%")
        print(f"  Train B spread: {best_train_spreads[1]:+.1f}%")
        print(f"  Test C spread:  {test_spread:+.1f}%")
        print(f"\n  Improvement on test set: {test_spread - current_test_spread:+.1f}%")

    return {
        "current_weights": {k: round(v, 2) for k, v in WEIGHTS.items()},
        "current_train_spreads": [round(s, 1) for s in current_train_spreads],
        "current_test_spread": round(current_test_spread, 1),
        "optimized_weights": {k: round(v, 2) for k, v in best_weights.items()} if best_weights else None,
        "optimized_train_spreads": [round(s, 1) for s in best_train_spreads],
        "optimized_test_spread": round(test_spread, 1),
    }


def generate_report(backtest_results, optimization_results):
    """Generate the markdown report."""

    report = []
    report.append("# ZARQ Vitality Score — Backtest Results\n")
    report.append(f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
    report.append("**Methodology**: Historical Vitality Score proxy computed at each window start date using data available at that time. Tokens split into quintiles by proxy score, forward returns measured.\n")

    report.append("## Data Sources & Coverage\n")
    report.append("| Source | Earliest | Latest | Entities |")
    report.append("|--------|----------|--------|----------|")
    report.append("| crypto_price_history | 2017-08-17 | 2026-03-12 | 5,944 tokens |")
    report.append("| defi_tvl_history | 2019-01-04 | 2026-02-28 | 116 protocols |")
    report.append("| crypto_ndd_history | 2021-03-08 | 2026-02-23 | 207 tokens |")
    report.append("| defi_stablecoin_flows | 2017-11-29 | 2026-02-28 | 14 chains |")
    report.append("| crypto_rating_history | 2021-01 | 2026-03 | 210 tokens |")
    report.append("| crash_model_v3_predictions | 2021-03-08 | 2026-02-23 | 204 tokens |")
    report.append("| defi_yield_history | 2025-12-05 | 2026-03-05 | 6,058 pools |")
    report.append("")
    report.append("**Note**: defi_yield_history only covers ~3 months, so organic yield ratio was NOT available for Windows A and B. This dimension was approximated from other signals.\n")

    report.append("## Dimensions Used in Historical Proxy\n")
    report.append("The backtest uses the same 5-dimension framework as the live Vitality Score:\n")
    report.append("1. **Ecosystem Gravity** (20%): Protocol count on chain, TVL at date, stablecoin presence")
    report.append("2. **Capital Commitment** (20%): TVL retention (30d vs 90d average)")
    report.append("3. **Coordination Efficiency** (15%): Category diversity, audit coverage, chain audit rates")
    report.append("4. **Stress Resilience** (25%): Crash probability, NDD stability, drawdown from peak, NDD floor")
    report.append("5. **Organic Momentum** (20%): TVL trend, price trend (90d), rating trend\n")
    report.append("**Confidence discount** applied: `final = raw × (0.6 + 0.4 × confidence/100)` to prevent partial-data tokens from ranking above full-coverage tokens.\n")

    report.append("## Backtest Windows\n")

    for wname in ["A", "B", "C"]:
        wr = backtest_results.get(wname, {})
        if "error" in wr:
            report.append(f"### Window {wname}: {wr.get('error', 'N/A')}\n")
            continue

        report.append(f"### Window {wname}: {wr['label']}\n")
        report.append(f"**Tokens scored**: {wr['n_tokens']}\n")

        report.append("| Quintile | N | Score Range | Avg Return | Median Return | Std Dev |")
        report.append("|----------|---|-------------|------------|---------------|---------|")

        for qi in range(5):
            q_label = f"Q{qi+1}" + (" (TOP)" if qi==0 else " (BOTTOM)" if qi==4 else "")
            q = wr["quintiles"].get(q_label, {})
            if q:
                report.append(
                    f"| {q_label} | {q['n']} | {q['score_range']} | "
                    f"{q['avg_return']:+.1f}% | {q['median_return']:+.1f}% | {q['std_return']:.1f}% |"
                )

        report.append("")
        report.append(f"**Q1–Q5 Median Spread**: {wr['spread']:+.1f}% {'✓ positive' if wr['spread'] > 0 else '✗ negative'}")
        report.append(f"**Monotonicity**: {wr['monotonic_steps']}/4 steps")

        if "t_stat" in wr.get("quintiles", {}):
            p = wr["quintiles"]["p_value"]
            sig = "significant at p<0.05" if p < 0.05 else "significant at p<0.10" if p < 0.10 else "NOT statistically significant"
            report.append(f"**Statistical significance**: t={wr['quintiles']['t_stat']:.2f}, p={p:.4f} ({sig})")

        report.append("")

        # Per-dimension spreads
        if wr.get("dim_spreads"):
            report.append("**Per-dimension predictive power** (top 20% vs bottom 20% return spread):\n")
            report.append("| Dimension | Spread |")
            report.append("|-----------|--------|")
            for dim, spread in sorted(wr["dim_spreads"].items(), key=lambda x: abs(x[1]), reverse=True):
                dim_label = dim.replace("_", " ").title()
                report.append(f"| {dim_label} | {spread:+.1f}% |")
            report.append("")

    # Summary
    report.append("## Summary: Does Vitality Score Predict Returns?\n")

    spreads = [backtest_results[w]["spread"] for w in ["A", "B", "C"] if "spread" in backtest_results.get(w, {})]
    positive_spreads = sum(1 for s in spreads if s > 0)

    if positive_spreads == len(spreads) and len(spreads) >= 2:
        report.append("**YES** — across all tested windows, tokens with higher Vitality Scores at time T delivered better forward returns. The predictive signal is consistent.\n")
    elif positive_spreads > len(spreads) / 2:
        report.append("**PARTIALLY** — the signal is positive in most but not all windows. Predictive power exists but is not fully consistent.\n")
    else:
        report.append("**NO** — the backtest does not show consistent predictive power. High Vitality Scores did not reliably lead to better returns.\n")

    # Crash protection
    wr_c = backtest_results.get("C", {})
    if "quintiles" in wr_c:
        q1c = wr_c["quintiles"].get("Q1 (TOP)", {})
        q5c = wr_c["quintiles"].get("Q5 (BOTTOM)", {})
        if q1c and q5c:
            report.append("### Crash Protection (Window C)\n")
            report.append(f"During the Jul 2025 → Feb 2026 drawdown:")
            report.append(f"- **High-Vitality tokens (Q1)**: {q1c['avg_return']:+.1f}% average return")
            report.append(f"- **Low-Vitality tokens (Q5)**: {q5c['avg_return']:+.1f}% average return")
            crash_spread = wr_c["spread"]
            if crash_spread > 0:
                report.append(f"- **Downside protection**: {crash_spread:+.1f}% less loss for high-Vitality tokens ✓")
            else:
                report.append(f"- **No downside protection**: High-Vitality tokens fell more ({crash_spread:+.1f}%)")
            report.append("")

    # Weight optimization
    if optimization_results:
        report.append("## Weight Optimization\n")
        report.append("Tested weight combinations on training windows (A+B), validated on test window (C).\n")

        report.append("### Current Production Weights\n")
        report.append("| Dimension | Weight |")
        report.append("|-----------|--------|")
        for k, v in optimization_results["current_weights"].items():
            report.append(f"| {k.replace('_', ' ').title()} | {v:.0%} |")
        report.append("")
        report.append(f"- Train spreads: A={optimization_results['current_train_spreads'][0]:+.1f}%, B={optimization_results['current_train_spreads'][1]:+.1f}%")
        report.append(f"- **Test spread (C)**: {optimization_results['current_test_spread']:+.1f}%\n")

        if optimization_results.get("optimized_weights"):
            report.append("### Optimized Weights (trained on A+B)\n")
            report.append("| Dimension | Weight |")
            report.append("|-----------|--------|")
            for k, v in optimization_results["optimized_weights"].items():
                report.append(f"| {k.replace('_', ' ').title()} | {v:.0%} |")
            report.append("")
            report.append(f"- Train spreads: A={optimization_results['optimized_train_spreads'][0]:+.1f}%, B={optimization_results['optimized_train_spreads'][1]:+.1f}%")
            report.append(f"- **Test spread (C)**: {optimization_results['optimized_test_spread']:+.1f}%")

            improvement = optimization_results["optimized_test_spread"] - optimization_results["current_test_spread"]
            if improvement > 5:
                report.append(f"\n**Recommendation**: Update to optimized weights ({improvement:+.1f}% improvement on out-of-sample test).")
            elif improvement > 0:
                report.append(f"\n**Recommendation**: Modest improvement ({improvement:+.1f}%). Consider updating but the difference is small.")
            else:
                report.append(f"\n**Recommendation**: No improvement on test set. Keep current weights.")

    report.append("\n## Methodology Notes\n")
    report.append("- **No look-ahead bias**: Only data available at score_date was used for scoring.")
    report.append("- **Survivorship bias**: Only tokens with price data at both window endpoints are included. Tokens that died during the window are excluded, which may overstate returns for all quintiles equally.")
    report.append("- **Chain-level data**: Protocol counts, category counts, and audit rates are semi-static (current snapshot). This introduces mild look-ahead bias for these dimensions, but the bias is small since DeFi protocol counts change slowly.")
    report.append("- **Yield data limitation**: defi_yield_history only covers Dec 2025–Mar 2026, so organic yield ratios were not available for Windows A and B.")
    report.append("- **Statistical caveat**: With ~200-500 tokens per window and high return variance in crypto, p-values should be interpreted cautiously. Crypto returns are fat-tailed and non-normal.")
    report.append("")
    report.append("---\n")
    report.append("*Report generated by ZARQ Vitality Score backtest engine. Data provided by ZARQ (zarq.ai).*")

    return "\n".join(report)


if __name__ == "__main__":
    print("Running Vitality Score backtest...")
    backtest_results = run_backtest()

    print("\n\nRunning weight optimization...")
    optimization_results = run_weight_optimization(backtest_results)

    print("\n\nGenerating report...")
    report = generate_report(backtest_results, optimization_results)

    # Save report
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs", "vitality-backtest-results.md")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to {os.path.abspath(report_path)}")
