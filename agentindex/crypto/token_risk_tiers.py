"""
Token Risk Tiers — assigns every token in crypto_trust.db a tier (T1-T5) with risk score.

Tier definitions:
  T1: Full Moody's rating (crypto_rating_daily)
  T2: NDD + price history (30+ days), no rating
  T3: Price history (30+ days) only
  T4: NDD data only (no price history)
  T5: DeFi protocol metadata only
"""

import json
import logging
import math
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = str(Path(__file__).parent / "crypto_trust.db")
CACHE_PATH = str(Path(__file__).parent / "token_tiers_cache.json")
SLUGS_PATH = str(Path(__file__).parent / "token_slugs.json")

ALERT_SCORE_MAP = {
    "SAFE": 100,
    "WATCH": 65,
    "WARNING": 35,
    "DISTRESS": 10,
    "CRITICAL": 5,
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def score_to_grade(score: int | None) -> str:
    """Map a 0-100 risk score to a letter grade."""
    if score is None:
        return "NR"
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "A-"
    if score >= 60:
        return "B+"
    if score >= 50:
        return "B"
    if score >= 40:
        return "B-"
    if score >= 30:
        return "C+"
    if score >= 20:
        return "C"
    if score >= 10:
        return "C-"
    if score >= 1:
        return "D"
    return "F"


def grade_color(grade: str) -> str:
    """Return a hex color for a risk grade pill."""
    if grade.startswith("A"):
        return "#16a34a"
    if grade.startswith("B"):
        return "#ca8a04"
    if grade.startswith("C"):
        return "#ea580c"
    return "#dc2626"


def _compute_ndd_risk_score(
    ndd: float | None,
    crash_probability: float | None,
    alert_level: str | None,
    market_cap_rank: int | None = None,
    include_mcap_bonus: bool = False,
) -> int:
    """Shared scoring formula for T2 and T4 tokens."""
    ndd = ndd if ndd is not None else 2.0
    crash_probability = crash_probability if crash_probability is not None else 0.5
    alert_level = alert_level if alert_level else "WATCH"

    ndd_score = _clamp((ndd - 1.0) / 4.0 * 100, 0, 100)
    crash_score = 100 - _clamp(crash_probability * 100, 0, 100)
    alert_score = ALERT_SCORE_MAP.get(alert_level.upper(), 50)

    risk_score = round(0.40 * ndd_score + 0.35 * crash_score + 0.25 * alert_score)

    if include_mcap_bonus and market_cap_rank and market_cap_rank <= 500:
        risk_score += 5

    return min(risk_score, 100)


def _compute_volatility_risk_score(prices: list[tuple[float]]) -> int:
    """Compute T3 volatility-based risk score from price history rows (close,)."""
    closes = [p[0] for p in prices if p[0] is not None and p[0] > 0]
    if len(closes) < 2:
        return 50  # default when insufficient data

    # Daily returns
    returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]

    # 30d volatility (use last 30 returns or all if fewer)
    recent = returns[-30:] if len(returns) >= 30 else returns
    if len(recent) >= 2:
        mean_r = sum(recent) / len(recent)
        var = sum((r - mean_r) ** 2 for r in recent) / (len(recent) - 1)
        daily_vol = math.sqrt(var)
    else:
        daily_vol = 0.0
    vol_pct = min(daily_vol * math.sqrt(30) * 100, 100)

    # 90d max drawdown (use last 90 closes or all)
    recent_closes = closes[-90:] if len(closes) >= 90 else closes
    peak = recent_closes[0]
    max_drawdown = 0.0
    for c in recent_closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak
        if dd > max_drawdown:
            max_drawdown = dd
    drawdown_pct = min(abs(max_drawdown) * 100, 100)

    # Price stability: fraction of days close is within ±5% of 30d SMA
    sma_window = min(30, len(closes))
    stable_days = 0
    total_days = 0
    for i in range(sma_window - 1, len(closes)):
        window = closes[max(0, i - sma_window + 1): i + 1]
        sma = sum(window) / len(window)
        if sma > 0 and abs(closes[i] - sma) / sma <= 0.05:
            stable_days += 1
        total_days += 1
    stability = stable_days / total_days if total_days > 0 else 0.5

    risk_score = round(
        100 - (0.40 * vol_pct + 0.30 * drawdown_pct + 0.30 * (1 - stability) * 100)
    )
    return max(0, min(risk_score, 100))


def compute_all_tiers() -> list[dict]:
    """Compute tier assignments and risk scores for all tokens in the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    tokens: dict[str, dict] = {}

    # ── T1: crypto_rating_daily (full Moody's rating) ──────────────────
    logger.info("Loading T1 tokens (crypto_rating_daily)...")
    cur.execute("""
        SELECT token_id, symbol, name, rating, score, price_usd, run_date
        FROM crypto_rating_daily
        WHERE (token_id, run_date) IN (
            SELECT token_id, MAX(run_date) FROM crypto_rating_daily GROUP BY token_id
        )
    """)
    t1_ids: set[str] = set()
    for row in cur.fetchall():
        tid = row["token_id"]
        t1_ids.add(tid)
        tokens[tid] = {
            "token_id": tid,
            "slug": tid,
            "symbol": row["symbol"],
            "name": row["name"],
            "tier": "T1",
            "risk_score": row["score"],
            "risk_grade": score_to_grade(row["score"]),
            "rating": row["rating"],
            "alert_level": None,
            "ndd": None,
            "crash_probability": None,
            "market_cap": None,
            "market_cap_rank": None,
            "price_usd": row["price_usd"],
            "volume_24h": None,
            "category": None,
            "chains": None,
            "tvl": None,
            "data_date": row["run_date"],
        }
    logger.info("T1: %d tokens", len(t1_ids))

    # ── Load NDD data (latest per token) ───────────────────────────────
    logger.info("Loading NDD data (crypto_ndd_daily)...")
    cur.execute("""
        SELECT token_id, symbol, name, market_cap_rank, ndd, crash_probability,
               alert_level, price_usd, market_cap, volume_24h, run_date
        FROM crypto_ndd_daily
        WHERE (token_id, run_date) IN (
            SELECT token_id, MAX(run_date) FROM crypto_ndd_daily GROUP BY token_id
        )
    """)
    ndd_data: dict[str, dict] = {}
    for row in cur.fetchall():
        ndd_data[row["token_id"]] = dict(row)

    # ── Load price history token IDs with 30+ days ─────────────────────
    logger.info("Loading price history token counts...")
    cur.execute("""
        SELECT token_id, COUNT(*) as day_count
        FROM crypto_price_history
        GROUP BY token_id
        HAVING day_count >= 30
    """)
    price_tokens: set[str] = set()
    for row in cur.fetchall():
        price_tokens.add(row["token_id"])

    # ── Load nerq_risk_signals for enrichment ──────────────────────────
    logger.info("Loading nerq_risk_signals...")
    cur.execute("""
        SELECT token_id, risk_level, trust_score, ndd_current, signal_date
        FROM nerq_risk_signals
        WHERE (token_id, signal_date) IN (
            SELECT token_id, MAX(signal_date) FROM nerq_risk_signals GROUP BY token_id
        )
    """)
    risk_signals: dict[str, dict] = {}
    for row in cur.fetchall():
        risk_signals[row["token_id"]] = dict(row)

    # ── Load defi_protocol_tokens for enrichment ───────────────────────
    logger.info("Loading defi_protocol_tokens...")
    cur.execute("""
        SELECT token_id, symbol, name, category, chains, tvl_latest
        FROM defi_protocol_tokens
    """)
    defi_data: dict[str, dict] = {}
    for row in cur.fetchall():
        defi_data[row["token_id"]] = dict(row)

    # ── Load pipeline status for symbol/name fallback ──────────────────
    logger.info("Loading pipeline status...")
    cur.execute("SELECT token_id, symbol, name FROM crypto_pipeline_status")
    pipeline: dict[str, dict] = {}
    for row in cur.fetchall():
        pipeline[row["token_id"]] = dict(row)

    # ── Assign T2: NDD + price history, not T1 ────────────────────────
    ndd_ids = set(ndd_data.keys())
    t2_ids = (ndd_ids & price_tokens) - t1_ids
    logger.info("Computing T2 tiers for %d tokens...", len(t2_ids))
    for tid in t2_ids:
        nd = ndd_data[tid]
        risk_score = _compute_ndd_risk_score(
            nd["ndd"], nd["crash_probability"], nd["alert_level"]
        )
        tokens[tid] = {
            "token_id": tid,
            "slug": tid,
            "symbol": nd["symbol"],
            "name": nd["name"],
            "tier": "T2",
            "risk_score": risk_score,
            "risk_grade": score_to_grade(risk_score),
            "rating": None,
            "alert_level": nd["alert_level"],
            "ndd": nd["ndd"],
            "crash_probability": nd["crash_probability"],
            "market_cap": nd["market_cap"],
            "market_cap_rank": nd["market_cap_rank"],
            "price_usd": nd["price_usd"],
            "volume_24h": nd["volume_24h"],
            "category": None,
            "chains": None,
            "tvl": None,
            "data_date": nd["run_date"],
        }
        # Enrich with nerq_risk_signals if available
        if tid in risk_signals:
            sig = risk_signals[tid]
            tokens[tid]["nerq_risk_level"] = sig["risk_level"]
            tokens[tid]["nerq_trust_score"] = sig["trust_score"]

    # ── Assign T3: price history only (no NDD, no rating) ─────────────
    t3_ids = price_tokens - t1_ids - ndd_ids
    logger.info("Computing T3 tiers for %d tokens...", len(t3_ids))
    for tid in t3_ids:
        cur.execute(
            "SELECT close FROM crypto_price_history WHERE token_id = ? ORDER BY date ASC",
            (tid,),
        )
        prices = cur.fetchall()
        risk_score = _compute_volatility_risk_score([(p["close"],) for p in prices])

        # Get symbol/name from pipeline or defi data
        sym = None
        nm = None
        price_usd = None
        if tid in pipeline:
            sym = pipeline[tid]["symbol"]
            nm = pipeline[tid]["name"]
        if tid in defi_data:
            sym = sym or defi_data[tid]["symbol"]
            nm = nm or defi_data[tid]["name"]
        # Last close as price
        if prices:
            price_usd = prices[-1]["close"]

        tokens[tid] = {
            "token_id": tid,
            "slug": tid,
            "symbol": sym,
            "name": nm,
            "tier": "T3",
            "risk_score": risk_score,
            "risk_grade": score_to_grade(risk_score),
            "rating": None,
            "alert_level": None,
            "ndd": None,
            "crash_probability": None,
            "market_cap": None,
            "market_cap_rank": None,
            "price_usd": price_usd,
            "volume_24h": None,
            "category": None,
            "chains": None,
            "tvl": None,
            "data_date": None,
        }

    # ── Assign T4: NDD only (no price history, no rating) ─────────────
    t4_ids = ndd_ids - t1_ids - price_tokens
    logger.info("Computing T4 tiers for %d tokens...", len(t4_ids))
    for tid in t4_ids:
        nd = ndd_data[tid]
        risk_score = _compute_ndd_risk_score(
            nd["ndd"],
            nd["crash_probability"],
            nd["alert_level"],
            market_cap_rank=nd["market_cap_rank"],
            include_mcap_bonus=True,
        )
        tokens[tid] = {
            "token_id": tid,
            "slug": tid,
            "symbol": nd["symbol"],
            "name": nd["name"],
            "tier": "T4",
            "risk_score": risk_score,
            "risk_grade": score_to_grade(risk_score),
            "rating": None,
            "alert_level": nd["alert_level"],
            "ndd": nd["ndd"],
            "crash_probability": nd["crash_probability"],
            "market_cap": nd["market_cap"],
            "market_cap_rank": nd["market_cap_rank"],
            "price_usd": nd["price_usd"],
            "volume_24h": nd["volume_24h"],
            "category": None,
            "chains": None,
            "tvl": None,
            "data_date": nd["run_date"],
        }

    # ── Assign T5: defi_protocol_tokens only ──────────────────────────
    existing_ids = set(tokens.keys())
    t5_ids = set(defi_data.keys()) - existing_ids
    logger.info("Assigning T5 tier for %d tokens...", len(t5_ids))
    for tid in t5_ids:
        dd = defi_data[tid]
        tokens[tid] = {
            "token_id": tid,
            "slug": tid,
            "symbol": dd["symbol"],
            "name": dd["name"],
            "tier": "T5",
            "risk_score": None,
            "risk_grade": "NR",
            "rating": None,
            "alert_level": None,
            "ndd": None,
            "crash_probability": None,
            "market_cap": None,
            "market_cap_rank": None,
            "price_usd": None,
            "volume_24h": None,
            "category": dd["category"],
            "chains": dd["chains"],
            "tvl": dd["tvl_latest"],
            "data_date": None,
        }

    # ── Enrich all tokens with defi metadata ───────────────────────────
    for tid, dd in defi_data.items():
        if tid in tokens and tokens[tid]["tier"] != "T5":
            tokens[tid]["category"] = dd["category"]
            tokens[tid]["chains"] = dd["chains"]
            tokens[tid]["tvl"] = dd["tvl_latest"]

    conn.close()

    result = list(tokens.values())
    logger.info(
        "Computed tiers for %d tokens: T1=%d T2=%d T3=%d T4=%d T5=%d",
        len(result),
        len(t1_ids),
        len(t2_ids),
        len(t3_ids),
        len(t4_ids),
        len(t5_ids),
    )
    return result


def save_tier_cache(tokens: list[dict]) -> None:
    """Save computed tiers to a JSON cache file."""
    with open(CACHE_PATH, "w") as f:
        json.dump(
            {
                "generated_at": datetime.utcnow().isoformat(),
                "count": len(tokens),
                "tokens": tokens,
            },
            f,
            indent=2,
            default=str,
        )
    logger.info("Saved tier cache with %d tokens to %s", len(tokens), CACHE_PATH)


def load_tier_cache() -> list[dict]:
    """Load tiers from the JSON cache file. Returns empty list if not found."""
    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)
        return data.get("tokens", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def generate_token_slugs(tokens: list[dict]) -> None:
    """Write token_slugs.json with all token slugs for URL routing."""
    slugs = {}
    for t in tokens:
        slugs[t["token_id"]] = {
            "symbol": t.get("symbol"),
            "name": t.get("name"),
            "tier": t["tier"],
            "risk_grade": t.get("risk_grade", "NR"),
        }
    with open(SLUGS_PATH, "w") as f:
        json.dump(slugs, f, indent=2)
    logger.info("Wrote %d token slugs to %s", len(slugs), SLUGS_PATH)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    tokens = compute_all_tiers()
    save_tier_cache(tokens)
    generate_token_slugs(tokens)

    # Print tier summary
    from collections import Counter
    tier_counts = Counter(t["tier"] for t in tokens)
    for tier in sorted(tier_counts):
        print(f"  {tier}: {tier_counts[tier]:,} tokens")
    print(f"  Total: {len(tokens):,} tokens")
