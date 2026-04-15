"""
ZARQ Vitality Score Engine
==========================
Measures ecosystem quality and coordination strength (0-100).
Complements the Trust Score (risk/crash focused).

5 Dimensions:
  1. Ecosystem Gravity (20%) — talent and capital attraction
  2. Capital Commitment (20%) — how deeply capital engages
  3. Coordination Efficiency (15%) — resource → infrastructure conversion
  4. Stress Resilience (25%) — density holds through drawdowns
  5. Organic Momentum (20%) — growth without artificial stimulus
"""

import json
import logging
import math
import sqlite3
import statistics
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = str(Path(__file__).parent / "crypto_trust.db")
CACHE_PATH = str(Path(__file__).parent / "vitality_cache.json")

WEIGHTS = {
    "ecosystem_gravity": 0.20,
    "capital_commitment": 0.20,
    "coordination_efficiency": 0.15,
    "stress_resilience": 0.25,
    "organic_momentum": 0.20,
}

# Chain name normalization (defi_protocol_tokens → defi_stablecoin_flows)
CHAIN_NORM = {
    "Binance": "BSC",
    "Avalanche": "Avalanche",
    "Polygon": "Polygon",
    "Ethereum": "Ethereum",
    "Solana": "Solana",
    "Arbitrum": "Arbitrum",
    "Optimism": "Optimism",
    "Base": "Base",
    "Tron": "Tron",
    "Fantom": "Fantom",
    "Gnosis": "Gnosis",
    "Moonbeam": "Moonbeam",
    "Cronos": "Cronos",
    "Celo": "Celo",
}

# Additional yield table normalization (defi_yields uses different names)
YIELD_NORM = {
    "Binance": "BSC",
    "TON": "Ton",
}

# Native L1/L2 token → chain name(s) in defi_protocol_tokens.chains
# These tokens ARE the chain — their ecosystem IS the chain's ecosystem
NATIVE_TOKEN_CHAINS = {
    "bitcoin":                  ["Bitcoin"],
    "ethereum":                 ["Ethereum"],
    "solana":                   ["Solana"],
    "sui":                      ["Sui"],
    "avalanche-2":              ["Avalanche"],
    "polkadot":                 ["Polkadot"],
    "binancecoin":              ["Binance"],
    "polygon-ecosystem-token":  ["Polygon"],
    "cardano":                  ["Cardano"],
    "cosmos":                   ["Cosmos"],
    "near":                     ["Near"],
    "tron":                     ["Tron"],
    "fantom":                   ["Fantom"],
    "arbitrum":                 ["Arbitrum"],
    "optimism":                 ["Optimism"],
    "base":                     ["Base"],
    "aptos":                    ["Aptos"],
    "the-open-network":         ["TON"],
    "mantle":                   ["Mantle"],
    "celo":                     ["Celo"],
    "harmony":                  ["Harmony"],
    "moonbeam":                 ["Moonbeam"],
    "kava":                     ["Kava"],
    "scroll":                   ["Scroll"],
    "blast":                    ["Blast"],
    "starknet":                 ["Starknet"],
    "sei-network":              ["Sei"],
    "manta-network":            ["Manta"],
    "cronos":                   ["Cronos"],
    "linea":                    ["Linea"],
    "injective-protocol":       ["Injective"],
    "celestia":                 ["Celestia"],
}

# Yield table chain names differ from defi_protocol_tokens chain names
CHAIN_YIELD_NORM = {
    "Binance": "BSC",
    "TON": "Ton",  # defi_yields uses "Ton", stablecoin_flows uses "TON"
}


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _chain_lookup(mapping, chain_name, default=0):
    """Look up a chain name in a mapping, trying multiple normalizations."""
    # Try exact match first
    if chain_name in mapping:
        return mapping[chain_name]
    # Try stablecoin normalization
    norm = CHAIN_NORM.get(chain_name)
    if norm and norm in mapping:
        return mapping[norm]
    # Try yield normalization
    ynorm = YIELD_NORM.get(chain_name)
    if ynorm and ynorm in mapping:
        return mapping[ynorm]
    return default


def _percentile_score(value, values_list, invert=False):
    """Score a value by its percentile rank within the dataset."""
    if not values_list or value is None:
        return None
    sorted_vals = sorted(values_list)
    rank = sum(1 for v in sorted_vals if v <= value) / len(sorted_vals)
    if invert:
        rank = 1.0 - rank
    return _clamp(rank * 100)


def _linear_trend(values):
    """Simple linear regression slope normalized to mean. Returns % change per period."""
    if not values or len(values) < 2:
        return None
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    if y_mean == 0:
        return 0
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0
    slope = num / den
    return slope / abs(y_mean) * 100  # pct change per period


def vitality_grade(score):
    """Map 0-100 vitality score to a letter grade."""
    if score is None:
        return "NR"
    if score >= 85:
        return "S"  # Superior
    if score >= 70:
        return "A"
    if score >= 55:
        return "B"
    if score >= 40:
        return "C"
    if score >= 25:
        return "D"
    return "F"


def vitality_color(grade):
    """Color for vitality grade."""
    if grade == "S":
        return "#0d9488"  # teal — exceptional
    if grade == "A":
        return "#16a34a"
    if grade == "B":
        return "#ca8a04"
    if grade == "C":
        return "#ea580c"
    return "#dc2626"


def vitality_label(score):
    """Human-readable label for vitality score."""
    if score is None:
        return "Not Rated"
    if score >= 85:
        return "Thriving ecosystem"
    if score >= 70:
        return "Strong ecosystem"
    if score >= 55:
        return "Developing ecosystem"
    if score >= 40:
        return "Emerging ecosystem"
    if score >= 25:
        return "Weak ecosystem"
    return "Minimal ecosystem"


# ── Dimension 1: Ecosystem Gravity ─────────────────────────────────────

def _compute_ecosystem_gravity(token_id, chain_protocol_counts, chain_stablecoin_totals,
                                protocol_data, all_tvls, all_mcap_ranks,
                                chain_dev_activity=None):
    """Protocol density on chain + TVL gravity + launch rate + developer activity."""
    sub_scores = []
    sources = []

    if protocol_data:
        chains = protocol_data.get("chains", [])
        tvl = protocol_data.get("tvl_latest")

        # Protocol count on token's chains
        if chains:
            max_protos = max(chain_protocol_counts.values()) if chain_protocol_counts else 1
            chain_scores = []
            for c in chains:
                count = chain_protocol_counts.get(c, 0)
                chain_scores.append(min(count / max(max_protos * 0.5, 1) * 100, 100))
            if chain_scores:
                sub_scores.append(sum(chain_scores) / len(chain_scores))
                sources.append("protocol_count")

        # TVL as gravity proxy
        if tvl and tvl > 0 and all_tvls:
            sub_scores.append(_percentile_score(tvl, all_tvls))
            sources.append("tvl")

        # Stablecoin presence on chains
        if chains:
            total_stable = sum(_chain_lookup(chain_stablecoin_totals, c) for c in chains)
            if total_stable > 0:
                all_stables = [v for v in chain_stablecoin_totals.values() if v > 0]
                if all_stables:
                    sub_scores.append(_percentile_score(total_stable, all_stables))
                    sources.append("stablecoin")

        # Developer activity on chains (from GitHub Dev Crawler)
        if chains and chain_dev_activity:
            dev_scores = []
            for c in chains:
                dev = chain_dev_activity.get(c)
                if dev:
                    # Score based on contributors (most meaningful signal)
                    contribs = dev["contributors"]
                    if contribs >= 500:
                        dev_scores.append(95)
                    elif contribs >= 200:
                        dev_scores.append(80)
                    elif contribs >= 50:
                        dev_scores.append(60)
                    elif contribs >= 10:
                        dev_scores.append(40)
                    else:
                        dev_scores.append(20)
            if dev_scores:
                sub_scores.append(max(dev_scores))  # Best chain's dev activity
                sources.append("developer_activity")

    # Fallback: market cap rank as gravity proxy
    if not sub_scores:
        mcap_rank = all_mcap_ranks.get(token_id)
        if mcap_rank is not None:
            # Top 10 = 90, top 50 = 70, top 200 = 50, top 500 = 30
            if mcap_rank <= 10:
                sub_scores.append(90)
            elif mcap_rank <= 50:
                sub_scores.append(70)
            elif mcap_rank <= 200:
                sub_scores.append(50)
            elif mcap_rank <= 500:
                sub_scores.append(30)
            else:
                sub_scores.append(15)
            sources.append("mcap_rank_fallback")

    if not sub_scores:
        return None, []
    return round(sum(sub_scores) / len(sub_scores), 1), sources


# ── Dimension 2: Capital Commitment ────────────────────────────────────

def _compute_capital_commitment(token_id, protocol_data, tvl_history,
                                 volume_mcap, yield_pool_counts, chain_yield_counts,
                                 chain_dex_volumes=None):
    """TVL retention, DEX velocity (inverted), volume churn, yield density.

    DEX velocity = DEX volume / TVL (inverted). Lower velocity means stickier
    capital — the Raoul Pal thesis. Heavily weighted when available.
    """
    sub_scores = []
    sources = []

    # TVL retention (latest vs 90d avg)
    if tvl_history and len(tvl_history) >= 30:
        recent = tvl_history[-30:]
        older = tvl_history[-90:-30] if len(tvl_history) >= 90 else tvl_history[:-30]
        if older:
            recent_avg = sum(recent) / len(recent)
            older_avg = sum(older) / len(older)
            if older_avg > 0:
                retention = min(recent_avg / older_avg, 2.0)
                sub_scores.append(_clamp(retention * 50))  # 1.0x = 50, 2.0x = 100
                sources.append("tvl_retention")

    # DEX velocity = monthly DEX volume / chain TVL (inverted)
    # Lower velocity = stickier capital = higher score
    if chain_dex_volumes and protocol_data:
        chains = protocol_data.get("chains", [])
        if chains and tvl_history:
            latest_tvl = tvl_history[-1] if tvl_history else 0
            if latest_tvl > 1_000_000:  # Only meaningful for >$1M TVL
                total_dex_vol = 0
                for c in chains:
                    dex = _chain_lookup(chain_dex_volumes, c)
                    if isinstance(dex, dict):
                        total_dex_vol += dex.get("monthly", 0)
                    elif isinstance(dex, (int, float)):
                        total_dex_vol += dex

                if total_dex_vol > 0:
                    velocity = total_dex_vol / latest_tvl
                    # Typical velocity range: 0.1 (very sticky) to 50+ (churny)
                    # Log-scale inversion: lower velocity = higher score
                    # velocity=0.5 → ~80, velocity=2 → ~60, velocity=10 → ~35, velocity=50 → ~10
                    log_vel = math.log10(max(velocity, 0.01))  # range ~ -2 to 2
                    vel_score = _clamp(80 - log_vel * 25)
                    # Double-weight: add twice because this is the strongest predictor
                    sub_scores.append(vel_score)
                    sub_scores.append(vel_score)
                    sources.append("dex_velocity")
                    sources.append("dex_velocity")

    # Volume-to-market-cap ratio (inverted — lower churn = better)
    vm = volume_mcap.get(token_id)
    if vm is not None:
        all_vms = [v for v in volume_mcap.values() if v is not None and v > 0]
        if all_vms:
            # Low velocity = committed capital. Invert the percentile.
            sub_scores.append(_percentile_score(vm, all_vms, invert=True))
            sources.append("volume_velocity")

    # Yield pool density on chains
    if protocol_data:
        chains = protocol_data.get("chains", [])
        if chains:
            densities = [_chain_lookup(chain_yield_counts, c) for c in chains]
            if any(d > 0 for d in densities):
                max_density = max(chain_yield_counts.values()) if chain_yield_counts else 1
                avg_density = sum(densities) / len(densities)
                sub_scores.append(_clamp(avg_density / max(max_density * 0.3, 1) * 100))
                sources.append("yield_density")

    # Fallback: market cap stability from price history CV
    if not sub_scores:
        sub_scores.append(50)  # neutral default
        sources.append("default")

    return round(sum(sub_scores) / len(sub_scores), 1), sources


# ── Dimension 3: Coordination Efficiency ───────────────────────────────

def _compute_coordination_efficiency(token_id, protocol_data, organic_ratio,
                                      chain_category_counts, chain_audit_rates):
    """Category diversity + audit coverage + organic yield ratio."""
    sub_scores = []
    sources = []

    if protocol_data:
        chains = protocol_data.get("chains", [])
        audit_count = protocol_data.get("audit_count", 0)

        # Category diversity on chain
        if chains:
            diversities = [_chain_lookup(chain_category_counts, c) for c in chains]
            if any(d > 0 for d in diversities):
                max_cats = max(chain_category_counts.values()) if chain_category_counts else 1
                avg_div = sum(diversities) / len(diversities)
                sub_scores.append(_clamp(avg_div / max(max_cats * 0.5, 1) * 100))
                sources.append("category_diversity")

        # Audit coverage
        if audit_count is not None:
            audit_score = {0: 10, 1: 50, 2: 75}.get(audit_count, 90)
            sub_scores.append(audit_score)
            sources.append("audit")

        # Chain-level audit rate
        if chains:
            rates = [_chain_lookup(chain_audit_rates, c) for c in chains]
            if any(r > 0 for r in rates):
                avg_rate = sum(rates) / len(rates)
                sub_scores.append(_clamp(avg_rate * 100))
                sources.append("chain_audit_rate")

    # Organic yield ratio (apy_base / total_apy) — UNIQUE DATA
    if organic_ratio is not None:
        sub_scores.append(_clamp(organic_ratio * 100))
        sources.append("organic_yield")

    if not sub_scores:
        sub_scores.append(40)  # neutral
        sources.append("default")

    return round(sum(sub_scores) / len(sub_scores), 1), sources


# ── Dimension 4: Stress Resilience ─────────────────────────────────────

def _compute_stress_resilience(token_id, ndd_history, crash_pred,
                                price_history, all_crash_probs):
    """NDD stability + crash prob inverse + recovery speed."""
    sub_scores = []
    sources = []

    # NDD stability (std dev of weekly NDD — lower = more stable)
    if ndd_history and len(ndd_history) >= 10:
        ndd_vals = [h for h in ndd_history if h is not None]
        if len(ndd_vals) >= 10:
            ndd_std = statistics.stdev(ndd_vals)
            ndd_mean = statistics.mean(ndd_vals)
            # CV = std/mean. Lower = more stable.
            cv = ndd_std / abs(ndd_mean) if ndd_mean != 0 else 1.0
            stability = _clamp(100 - cv * 100)
            sub_scores.append(stability)
            sources.append("ndd_stability")

            # NDD floor
            ndd_min = min(ndd_vals)
            if ndd_min >= 3.0:
                sub_scores.append(90)
            elif ndd_min >= 2.0:
                sub_scores.append(70)
            elif ndd_min >= 1.0:
                sub_scores.append(40)
            else:
                sub_scores.append(15)
            sources.append("ndd_floor")

    # Crash probability inverse
    if crash_pred is not None:
        crash_score = _clamp(100 - crash_pred * 100)
        sub_scores.append(crash_score)
        sources.append("crash_prob_inv")

    # Price drawdown recovery
    if price_history and len(price_history) >= 90:
        closes = [p for p in price_history if p is not None and p > 0]
        if len(closes) >= 90:
            # Max drawdown in last 365 days
            peak = closes[0]
            max_dd = 0
            for c in closes:
                if c > peak:
                    peak = c
                dd = (peak - c) / peak
                if dd > max_dd:
                    max_dd = dd
            # Less drawdown = better
            dd_score = _clamp(100 - max_dd * 100)
            sub_scores.append(dd_score)
            sources.append("drawdown")

    if not sub_scores:
        return None, []
    return round(sum(sub_scores) / len(sub_scores), 1), sources


# ── Dimension 5: Organic Momentum ─────────────────────────────────────

def _compute_organic_momentum(token_id, tvl_history, price_history_90d,
                               volume_history_90d, rating_history,
                               ndd_trend, organic_yield_trend):
    """Rating trend + NDD trend + TVL momentum + yield growth."""
    sub_scores = []
    sources = []

    # TVL momentum (90-day trend)
    if tvl_history and len(tvl_history) >= 30:
        recent_90 = tvl_history[-90:] if len(tvl_history) >= 90 else tvl_history
        trend = _linear_trend(recent_90)
        if trend is not None:
            # Positive trend = good. Cap at +/- 50% per period
            sub_scores.append(_clamp(50 + trend * 2))
            sources.append("tvl_momentum")

    # Rating trend (latest vs 6 months ago)
    if rating_history and len(rating_history) >= 2:
        latest = rating_history[-1]
        older = rating_history[max(0, len(rating_history) - 7)]  # ~6 months ago
        if latest is not None and older is not None:
            diff = latest - older
            # +10 pts = great improvement, -10 = decline
            sub_scores.append(_clamp(50 + diff * 3))
            sources.append("rating_trend")

    # NDD trend (categorical: IMPROVING, STABLE, SLIDING, FALLING, FREEFALL, UNKNOWN)
    if ndd_trend is not None:
        trend_map = {"IMPROVING": 80, "STABLE": 60, "UNKNOWN": 50, "SLIDING": 35, "FALLING": 20, "FREEFALL": 5}
        trend_score = trend_map.get(str(ndd_trend).upper(), 50)
        sub_scores.append(trend_score)
        sources.append("ndd_trend")

    # Volume momentum
    if volume_history_90d and len(volume_history_90d) >= 30:
        trend = _linear_trend(volume_history_90d)
        if trend is not None:
            sub_scores.append(_clamp(50 + trend))
            sources.append("volume_momentum")

    # Organic yield trend
    if organic_yield_trend is not None:
        sub_scores.append(_clamp(50 + organic_yield_trend * 2))
        sources.append("organic_yield_trend")

    if not sub_scores:
        return None, []
    return round(sum(sub_scores) / len(sub_scores), 1), sources


# ── Main computation ───────────────────────────────────────────────────

def compute_vitality_scores(tier_filter=None):
    """Compute Vitality Scores for all tokens with sufficient data."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.row_factory = sqlite3.Row

    logger.info("Loading base data...")

    # ── Load T1 token list ──
    tokens = {}
    rows = conn.execute("""
        SELECT token_id, symbol, name, score, rating
        FROM crypto_rating_daily
        WHERE (token_id, run_date) IN (
            SELECT token_id, MAX(run_date) FROM crypto_rating_daily GROUP BY token_id
        )
    """).fetchall()
    for r in rows:
        tokens[r["token_id"]] = {
            "token_id": r["token_id"],
            "symbol": r["symbol"],
            "name": r["name"],
            "trust_score": r["score"],
            "trust_rating": r["rating"],
        }
    logger.info("Loaded %d rated tokens", len(tokens))

    # Also add T2/T4 tokens if no filter
    if tier_filter is None or tier_filter != "T1":
        ndd_rows = conn.execute("""
            SELECT token_id, symbol, name, market_cap_rank
            FROM crypto_ndd_daily
            WHERE (token_id, run_date) IN (
                SELECT token_id, MAX(run_date) FROM crypto_ndd_daily GROUP BY token_id
            )
            AND token_id NOT IN (SELECT DISTINCT token_id FROM crypto_rating_daily)
        """).fetchall()
        for r in ndd_rows:
            tokens[r["token_id"]] = {
                "token_id": r["token_id"],
                "symbol": r["symbol"],
                "name": r["name"],
                "trust_score": None,
                "trust_rating": None,
            }
        logger.info("Added %d NDD-only tokens, total: %d", len(ndd_rows), len(tokens))

    # ── Pre-load chain-level aggregates ──

    # Protocol counts per chain
    logger.info("Computing chain-level aggregates...")
    chain_protocol_counts = {}
    for row in conn.execute("SELECT chains FROM defi_protocol_tokens WHERE chains IS NOT NULL"):
        try:
            chains = json.loads(row["chains"])
            for c in chains:
                chain_protocol_counts[c] = chain_protocol_counts.get(c, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass

    # Stablecoin totals per chain (latest)
    chain_stablecoin_totals = {}
    for row in conn.execute("""
        SELECT chain, total_circulating
        FROM defi_stablecoin_flows
        WHERE (chain, date) IN (
            SELECT chain, MAX(date) FROM defi_stablecoin_flows GROUP BY chain
        )
    """):
        chain_stablecoin_totals[row["chain"]] = row["total_circulating"] or 0

    # Category counts per chain
    chain_category_counts = {}
    for row in conn.execute("SELECT chains, category FROM defi_protocol_tokens WHERE chains IS NOT NULL AND category IS NOT NULL"):
        try:
            chains = json.loads(row["chains"])
            cat = row["category"]
            for c in chains:
                if c not in chain_category_counts:
                    chain_category_counts[c] = set()
                chain_category_counts[c].add(cat)
        except (json.JSONDecodeError, TypeError):
            pass
    chain_category_counts = {k: len(v) for k, v in chain_category_counts.items()}

    # Audit rates per chain
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

    # Yield pool counts per chain
    chain_yield_counts = {}
    for row in conn.execute("SELECT chain, COUNT(*) as cnt FROM defi_yields GROUP BY chain"):
        chain_yield_counts[row["chain"]] = row["cnt"]

    # All TVL values (for percentile scoring)
    all_tvls = [row[0] for row in conn.execute(
        "SELECT tvl_latest FROM defi_protocol_tokens WHERE tvl_latest > 0")]

    # Market cap ranks
    all_mcap_ranks = {}
    for row in conn.execute("""
        SELECT token_id, market_cap_rank FROM crypto_ndd_daily
        WHERE (token_id, run_date) IN (
            SELECT token_id, MAX(run_date) FROM crypto_ndd_daily GROUP BY token_id
        ) AND market_cap_rank IS NOT NULL
    """):
        all_mcap_ranks[row["token_id"]] = row["market_cap_rank"]

    # Volume / market cap ratios
    volume_mcap = {}
    for row in conn.execute("""
        SELECT token_id, volume_24h, market_cap FROM crypto_ndd_daily
        WHERE (token_id, run_date) IN (
            SELECT token_id, MAX(run_date) FROM crypto_ndd_daily GROUP BY token_id
        ) AND volume_24h > 0 AND market_cap > 0
    """):
        volume_mcap[row["token_id"]] = row["volume_24h"] / row["market_cap"]

    # Developer activity per chain (from GitHub Dev Crawler, System 10)
    chain_dev_activity = {}
    try:
        # Check if table exists
        has_dev_table = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='chain_developer_activity'
        """).fetchone()
        if has_dev_table:
            for row in conn.execute("""
                SELECT chain, contributors_30d, commits_30d, new_repos_30d
                FROM chain_developer_activity
                WHERE (chain, fetched_at) IN (
                    SELECT chain, MAX(fetched_at) FROM chain_developer_activity GROUP BY chain
                )
            """):
                chain_dev_activity[row["chain"]] = {
                    "contributors": row["contributors_30d"] or 0,
                    "commits": row["commits_30d"] or 0,
                    "new_repos": row["new_repos_30d"] or 0,
                }
            if chain_dev_activity:
                logger.info("Loaded developer activity for %d chains", len(chain_dev_activity))
    except Exception as e:
        logger.debug("Developer activity data not available: %s", e)

    # ── Per-token DeFi protocol data ──
    logger.info("Loading per-token protocol data...")
    protocol_data_by_token = {}
    for row in conn.execute("""
        SELECT token_id, chains, tvl_latest, audit_count, protocol_id, listed_at
        FROM defi_protocol_tokens
        WHERE token_id IS NOT NULL
    """):
        try:
            chains = json.loads(row["chains"]) if row["chains"] else []
        except (json.JSONDecodeError, TypeError):
            chains = []
        protocol_data_by_token[row["token_id"]] = {
            "chains": chains,
            "tvl_latest": row["tvl_latest"],
            "audit_count": row["audit_count"],
            "protocol_id": row["protocol_id"],
            "listed_at": row["listed_at"],
        }

    # ── TVL history by protocol_id ──
    logger.info("Loading TVL history...")
    tvl_history_by_protocol = {}
    for row in conn.execute("""
        SELECT protocol_id, tvl_usd FROM defi_tvl_history
        ORDER BY protocol_id, date ASC
    """):
        pid = row["protocol_id"]
        if pid not in tvl_history_by_protocol:
            tvl_history_by_protocol[pid] = []
        tvl_history_by_protocol[pid].append(row["tvl_usd"])

    # ── NDD history per token ──
    logger.info("Loading NDD history...")
    ndd_history_by_token = {}
    for row in conn.execute("""
        SELECT token_id, ndd FROM crypto_ndd_history
        ORDER BY token_id, week_date ASC
    """):
        tid = row["token_id"]
        if tid not in ndd_history_by_token:
            ndd_history_by_token[tid] = []
        ndd_history_by_token[tid].append(row["ndd"])

    # ── Crash predictions ──
    logger.info("Loading crash predictions...")
    crash_preds = {}
    for row in conn.execute("""
        SELECT token_id, crash_prob_v3 FROM crash_model_v3_predictions
        WHERE (token_id, date) IN (
            SELECT token_id, MAX(date) FROM crash_model_v3_predictions GROUP BY token_id
        )
    """):
        crash_preds[row["token_id"]] = row["crash_prob_v3"]

    all_crash_probs = [v for v in crash_preds.values() if v is not None]

    # ── Price history (last 365 days closes) ──
    logger.info("Loading price history...")
    price_history_by_token = {}
    cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    for row in conn.execute("""
        SELECT token_id, close FROM crypto_price_history
        WHERE date >= ? ORDER BY token_id, date ASC
    """, (cutoff,)):
        tid = row["token_id"]
        if tid not in price_history_by_token:
            price_history_by_token[tid] = []
        price_history_by_token[tid].append(row["close"])

    # Volume history (last 90 days)
    volume_history_by_token = {}
    vol_cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    for row in conn.execute("""
        SELECT token_id, volume FROM crypto_price_history
        WHERE date >= ? AND volume IS NOT NULL ORDER BY token_id, date ASC
    """, (vol_cutoff,)):
        tid = row["token_id"]
        if tid not in volume_history_by_token:
            volume_history_by_token[tid] = []
        volume_history_by_token[tid].append(row["volume"])

    # ── Rating history (monthly scores) ──
    logger.info("Loading rating history...")
    rating_history_by_token = {}
    for row in conn.execute("""
        SELECT token_id, score FROM crypto_rating_history
        ORDER BY token_id, year_month ASC
    """):
        tid = row["token_id"]
        if tid not in rating_history_by_token:
            rating_history_by_token[tid] = []
        rating_history_by_token[tid].append(row["score"])

    # ── NDD trends ──
    ndd_trends = {}
    for row in conn.execute("""
        SELECT token_id, ndd_trend FROM crypto_ndd_daily
        WHERE (token_id, run_date) IN (
            SELECT token_id, MAX(run_date) FROM crypto_ndd_daily GROUP BY token_id
        ) AND ndd_trend IS NOT NULL
    """):
        ndd_trends[row["token_id"]] = row["ndd_trend"]

    # ── Organic yield ratios ──
    logger.info("Loading organic yield data...")
    organic_ratios_by_protocol = {}
    organic_yield_trends = {}
    for row in conn.execute("""
        SELECT y.project, AVG(CASE WHEN yh.apy_base + yh.apy_reward > 0
            THEN yh.apy_base / (yh.apy_base + yh.apy_reward) ELSE NULL END) as avg_organic
        FROM defi_yield_history yh
        JOIN defi_yields y ON yh.pool_id = y.pool_id
        WHERE yh.apy_base IS NOT NULL
        GROUP BY y.project
    """):
        if row["avg_organic"] is not None:
            organic_ratios_by_protocol[row["project"]] = row["avg_organic"]

    # ── Chain-level data for native L1/L2 tokens ──
    logger.info("Loading chain-level data for native tokens...")

    # Aggregate TVL per chain from defi_tvl_history (sum protocol TVLs on each chain)
    # First, map protocol_id → chains
    protocol_chains = {}
    for row in conn.execute("SELECT protocol_id, chains FROM defi_protocol_tokens WHERE chains IS NOT NULL AND protocol_id IS NOT NULL"):
        try:
            protocol_chains[row["protocol_id"]] = json.loads(row["chains"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Build chain TVL history by summing protocol TVLs per date
    chain_tvl_by_date = {}  # chain → {date → total_tvl}
    for row in conn.execute("SELECT protocol_id, date, tvl_usd FROM defi_tvl_history WHERE tvl_usd IS NOT NULL"):
        pid = row["protocol_id"]
        chains_for_proto = protocol_chains.get(pid, [])
        for c in chains_for_proto:
            if c not in chain_tvl_by_date:
                chain_tvl_by_date[c] = {}
            d = row["date"]
            chain_tvl_by_date[c][d] = chain_tvl_by_date[c].get(d, 0) + (row["tvl_usd"] or 0)

    # Convert to sorted lists
    chain_tvl_history = {}
    for chain, date_tvl in chain_tvl_by_date.items():
        sorted_dates = sorted(date_tvl.keys())
        chain_tvl_history[chain] = [date_tvl[d] for d in sorted_dates]

    # Chain-level organic yield ratios (from defi_yields)
    chain_organic_ratios = {}
    for row in conn.execute("""
        SELECT chain, AVG(CASE WHEN apy_base + apy_reward > 0
            THEN apy_base / (apy_base + apy_reward) ELSE NULL END) as avg_org
        FROM defi_yields
        WHERE apy_base IS NOT NULL AND apy_reward IS NOT NULL
        GROUP BY chain
    """):
        if row["avg_org"] is not None:
            chain_organic_ratios[row["chain"]] = row["avg_org"]

    # Chain-level stablecoin history for stress analysis
    chain_stablecoin_history = {}
    for row in conn.execute("""
        SELECT chain, total_circulating FROM defi_stablecoin_flows
        ORDER BY chain, date ASC
    """):
        c = row["chain"]
        if c not in chain_stablecoin_history:
            chain_stablecoin_history[c] = []
        chain_stablecoin_history[c].append(row["total_circulating"] or 0)

    # ── Chain-level DEX volumes (from DeFiLlama crawler) ──
    logger.info("Loading DEX volume data...")
    chain_dex_volumes = {}  # chain -> {daily_volume, monthly_volume}
    try:
        for row in conn.execute("SELECT chain, daily_volume, monthly_volume FROM chain_dex_volumes"):
            chain_dex_volumes[row["chain"]] = {
                "daily": row["daily_volume"] or 0,
                "monthly": row["monthly_volume"] or 0,
            }
        logger.info("Loaded DEX volumes for %d chains", len(chain_dex_volumes))
    except sqlite3.OperationalError:
        logger.warning("chain_dex_volumes table not found — run defi_dex_volumes crawler first")

    conn.close()

    # ── Compute scores ──
    logger.info("Computing Vitality Scores for %d tokens...", len(tokens))
    results = []

    for token_id, tdata in tokens.items():
        pdata = protocol_data_by_token.get(token_id)
        protocol_id = pdata["protocol_id"] if pdata else None
        tvl_hist = tvl_history_by_protocol.get(protocol_id, []) if protocol_id else []
        ndd_hist = ndd_history_by_token.get(token_id, [])
        crash_pred = crash_preds.get(token_id)
        price_hist = price_history_by_token.get(token_id, [])
        vol_hist = volume_history_by_token.get(token_id, [])
        rating_hist = rating_history_by_token.get(token_id, [])
        ndd_trend = ndd_trends.get(token_id)
        organic_ratio = organic_ratios_by_protocol.get(protocol_id) if protocol_id else None

        # ── NATIVE L1/L2 TOKEN OVERRIDE ──
        # If this token IS the native token of a chain, use chain-level data
        native_chains = NATIVE_TOKEN_CHAINS.get(token_id)
        is_native = native_chains is not None

        if is_native:
            # Synthesize protocol_data from chain-level aggregates
            chain_name = native_chains[0]  # primary chain
            chain_total_tvl = sum(
                chain_tvl_history.get(c, [0])[-1] if chain_tvl_history.get(c) else 0
                for c in native_chains
            )
            chain_total_protos = sum(chain_protocol_counts.get(c, 0) for c in native_chains)
            chain_max_audits = 0
            for c in native_chains:
                chain_max_audits = max(chain_max_audits, chain_audit_counts.get(c, 0))

            pdata = {
                "chains": native_chains,
                "tvl_latest": chain_total_tvl,
                "audit_count": min(chain_max_audits, 3),  # cap at 3 (= 90 score)
                "protocol_id": None,
                "listed_at": None,
            }

            # Use chain-level TVL history (aggregated across all protocols on chain)
            tvl_hist = chain_tvl_history.get(chain_name, [])

            # Use chain-level organic yield ratio
            yield_chain_name = CHAIN_YIELD_NORM.get(chain_name, chain_name)
            organic_ratio = chain_organic_ratios.get(yield_chain_name)

        # Compute each dimension
        d1, s1 = _compute_ecosystem_gravity(
            token_id, chain_protocol_counts, chain_stablecoin_totals,
            pdata, all_tvls, all_mcap_ranks, chain_dev_activity)

        d2, s2 = _compute_capital_commitment(
            token_id, pdata, tvl_hist, volume_mcap,
            chain_yield_counts, chain_yield_counts, chain_dex_volumes)

        d3, s3 = _compute_coordination_efficiency(
            token_id, pdata, organic_ratio,
            chain_category_counts, chain_audit_rates)

        d4, s4 = _compute_stress_resilience(
            token_id, ndd_hist, crash_pred, price_hist, all_crash_probs)

        d5, s5 = _compute_organic_momentum(
            token_id, tvl_hist, price_hist[-90:] if price_hist else [],
            vol_hist, rating_hist, ndd_trend, None)

        # Weighted composite — only include dimensions with data
        dims = {"ecosystem_gravity": d1, "capital_commitment": d2,
                "coordination_efficiency": d3, "stress_resilience": d4,
                "organic_momentum": d5}

        available = {k: v for k, v in dims.items() if v is not None}
        if not available:
            continue

        # Re-weight based on available dimensions
        total_weight = sum(WEIGHTS[k] for k in available)
        if total_weight == 0:
            continue

        weighted_sum = sum(v * WEIGHTS[k] / total_weight for k, v in available.items())
        confidence = round(len(available) / 5 * 100)
        # Confidence discount: partial-data tokens can't outrank full-coverage tokens
        # 100% conf → 1.0x, 60% conf → 0.84x, 40% conf → 0.76x, 20% conf → 0.68x
        confidence_factor = 0.6 + 0.4 * (confidence / 100)
        vitality = round(_clamp(weighted_sum * confidence_factor), 1)

        # Data sources tracking
        all_sources = s1 + s2 + s3 + s4 + s5
        data_coverage = {
            "dimensions_computed": len(available),
            "confidence_pct": confidence,
            "sources": list(set(all_sources)),
        }

        results.append({
            "token_id": token_id,
            "symbol": tdata.get("symbol"),
            "name": tdata.get("name"),
            "vitality_score": vitality,
            "vitality_grade": vitality_grade(vitality),
            "ecosystem_gravity": d1,
            "capital_commitment": d2,
            "coordination_efficiency": d3,
            "stress_resilience": d4,
            "organic_momentum": d5,
            "trust_score": tdata.get("trust_score"),
            "trust_rating": tdata.get("trust_rating"),
            "confidence": confidence,
            "data_coverage": json.dumps(data_coverage),
            "computed_at": datetime.utcnow().isoformat(),
        })

    results.sort(key=lambda r: r["vitality_score"], reverse=True)
    logger.info("Computed Vitality Scores for %d tokens", len(results))
    return results


def save_vitality_scores(results):
    """Save results to SQLite table and JSON cache."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vitality_scores (
            token_id TEXT PRIMARY KEY,
            symbol TEXT,
            name TEXT,
            vitality_score REAL,
            vitality_grade TEXT,
            ecosystem_gravity REAL,
            capital_commitment REAL,
            coordination_efficiency REAL,
            stress_resilience REAL,
            organic_momentum REAL,
            trust_score REAL,
            trust_rating TEXT,
            confidence INTEGER,
            data_coverage TEXT,
            computed_at TEXT
        )
    """)

    import time as _time
    from agentindex.crypto.dual_write import dual_delete, dual_execute
    for attempt in range(5):
        try:
            dual_delete(conn, "DELETE FROM vitality_scores")
            for r in results:
                dual_execute(conn, """
                    INSERT INTO vitality_scores (
                        token_id, symbol, name, vitality_score, vitality_grade,
                        ecosystem_gravity, capital_commitment, coordination_efficiency,
                        stress_resilience, organic_momentum, trust_score, trust_rating,
                        confidence, data_coverage, computed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r["token_id"], r["symbol"], r["name"],
                    r["vitality_score"], r["vitality_grade"],
                    r["ecosystem_gravity"], r["capital_commitment"],
                    r["coordination_efficiency"], r["stress_resilience"],
                    r["organic_momentum"], r["trust_score"], r["trust_rating"],
                    r["confidence"], r["data_coverage"], r["computed_at"],
                ))
            conn.commit()
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 4:
                logger.warning("SQLite locked, retry %d/5 in %ds", attempt + 1, 2 ** attempt)
                conn.rollback()
                _time.sleep(2 ** attempt)
            else:
                raise

    conn.close()
    logger.info("Saved %d vitality scores to DB", len(results))

    # Also save JSON cache
    with open(CACHE_PATH, "w") as f:
        json.dump({
            "generated_at": datetime.utcnow().isoformat(),
            "count": len(results),
            "scores": results,
        }, f, indent=2, default=str)
    logger.info("Saved vitality cache to %s", CACHE_PATH)


def load_vitality_scores():
    """Load vitality scores from DB."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM vitality_scores ORDER BY vitality_score DESC").fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def get_vitality_for_token(token_id):
    """Get vitality score for a single token. Returns dict or None."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM vitality_scores WHERE token_id = ?", (token_id,)).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = compute_vitality_scores()
    save_vitality_scores(results)

    # Summary
    print(f"\n{'='*60}")
    print(f"ZARQ Vitality Score — {len(results)} tokens scored")
    print(f"{'='*60}")

    # Distribution
    grades = {}
    for r in results:
        g = r["vitality_grade"]
        grades[g] = grades.get(g, 0) + 1
    print("\nGrade Distribution:")
    for g in ["S", "A", "B", "C", "D", "F"]:
        print(f"  {g}: {grades.get(g, 0)}")

    # Confidence stats
    confs = [r["confidence"] for r in results]
    print(f"\nConfidence: avg={sum(confs)/len(confs):.0f}%, "
          f"100%={sum(1 for c in confs if c == 100)}, "
          f"<60%={sum(1 for c in confs if c < 60)}")

    scores = [r["vitality_score"] for r in results]
    print(f"\nScore range: {min(scores):.1f} — {max(scores):.1f}")
    print(f"Mean: {sum(scores)/len(scores):.1f}, "
          f"Median: {sorted(scores)[len(scores)//2]:.1f}")

    # Top 10
    print(f"\n{'─'*60}")
    print("TOP 10 by Vitality Score:")
    print(f"{'Token':<25} {'Vitality':>8} {'Grade':>5} {'Trust':>7} {'Conf':>5}")
    for r in results[:10]:
        name = (r["name"] or r["token_id"])[:24]
        trust = r["trust_rating"] or "—"
        print(f"{name:<25} {r['vitality_score']:>7.1f} {r['vitality_grade']:>5} "
              f"{trust:>7} {r['confidence']:>4}%")

    # Bottom 10
    print(f"\n{'─'*60}")
    print("BOTTOM 10 by Vitality Score:")
    for r in results[-10:]:
        name = (r["name"] or r["token_id"])[:24]
        trust = r["trust_rating"] or "—"
        print(f"{name:<25} {r['vitality_score']:>7.1f} {r['vitality_grade']:>5} "
              f"{trust:>7} {r['confidence']:>4}%")
