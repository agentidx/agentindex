"""
Sprint 9 Extension: Yield Divergence Engine
Beräknar WOW-insikter från historisk APY/TVL data.

Signaler:
  1. TVL/APY Divergens    — TVL faller medan APY stiger (exit-scam mönster)
  2. Emission Cliff       — reward-APY kurvan pekar mot slut
  3. APY Spike            — plötslig APY-ökning (pump)
  4. TVL Exodus           — stor TVL-utflöde senaste 7 dagar
  5. Reward Collapse      — reward APY sjunker snabbt (emission tar slut)
  6. Sustainable Yield    — base APY håller sig stabil (bra signal)

Alla signaler 0-100 score + human-readable insight text.
"""

import os
import sqlite3
from typing import Optional
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)).replace("/agentindex-factory/", "/agentindex/"),
    "crypto_trust.db",
)


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_pool_history(conn, pool_id: str, days: int = 30) -> list:
    """Hämta historik för en pool, sorterad datum ASC."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT date, tvl_usd, apy, apy_base, apy_reward, il_7d
        FROM defi_yield_history
        WHERE pool_id = ? AND date >= ?
        ORDER BY date ASC
    """, (pool_id, cutoff)).fetchall()
    return [dict(r) for r in rows]


def compute_divergence_signals(pool_id: str, history: list) -> dict:
    """
    Beräkna alla divergens-signaler för en pool baserat på historik.
    Returnerar signals-dict med score + text per signal.
    """
    if len(history) < 7:
        return {"insufficient_data": True, "data_points": len(history)}

    # Dela upp i perioder
    recent = history[-7:]    # senaste 7 dagar
    older = history[-14:-7] if len(history) >= 14 else history[:7]
    oldest = history[:7]

    def safe_avg(data, key):
        vals = [d[key] for d in data if d.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    def safe_last(data, key):
        for d in reversed(data):
            if d.get(key) is not None:
                return d[key]
        return None

    # Värden
    tvl_now = safe_last(recent, "tvl_usd")
    tvl_7d_ago = safe_last(older, "tvl_usd")
    tvl_30d_ago = safe_last(oldest, "tvl_usd")

    apy_now = safe_last(recent, "apy")
    apy_7d_ago = safe_last(older, "apy")
    apy_30d_ago = safe_last(oldest, "apy")

    reward_now = safe_last(recent, "apy_reward")
    reward_7d_ago = safe_last(older, "apy_reward")

    base_now = safe_last(recent, "apy_base")
    base_30d_ago = safe_last(oldest, "apy_base")

    signals = {}

    # ── Signal 1: TVL/APY Divergens ─────────────────────────────────────────
    # TVL sjunker + APY stiger = smarta pengar lämnar medan yield pumpar för att locka nya
    div_score = 0
    div_text = None
    if tvl_now and tvl_7d_ago and apy_now and apy_7d_ago and tvl_7d_ago > 0:
        tvl_change = (tvl_now - tvl_7d_ago) / tvl_7d_ago
        apy_change = (apy_now - apy_7d_ago) / apy_7d_ago if apy_7d_ago > 0 else 0
        if tvl_change < -0.05 and apy_change > 0.1:
            div_score = min(round(abs(tvl_change) * 100 + apy_change * 50), 100)
            div_text = (f"TVL {tvl_change*100:.1f}% medan APY +{apy_change*100:.1f}% "
                       f"senaste 7 dagarna — smarta pengar lämnar")
        elif tvl_change < -0.15:
            div_score = min(round(abs(tvl_change) * 80), 100)
            div_text = f"TVL exodus: -{abs(tvl_change)*100:.1f}% senaste 7 dagar"

    signals["tvl_apy_divergence"] = {
        "score": div_score,
        "signal": "TVL/APY Divergens",
        "text": div_text,
        "tvl_change_7d": round((tvl_now - tvl_7d_ago) / tvl_7d_ago * 100, 1) if tvl_now and tvl_7d_ago and tvl_7d_ago > 0 else None,
        "apy_change_7d": round((apy_now - apy_7d_ago) / apy_7d_ago * 100, 1) if apy_now and apy_7d_ago and apy_7d_ago > 0 else None,
    }

    # ── Signal 2: APY Spike ──────────────────────────────────────────────────
    # APY plötsligt +100%+ = emission-pump, lockar likviditet som snart flyr
    spike_score = 0
    spike_text = None
    if apy_now and apy_7d_ago and apy_7d_ago > 0:
        spike = (apy_now - apy_7d_ago) / apy_7d_ago
        if spike > 1.0:   # +100%
            spike_score = min(round(spike * 40), 100)
            spike_text = f"APY spike +{spike*100:.0f}% senaste 7 dagar — emission-pump detekterad"
        elif spike > 0.5:  # +50%
            spike_score = min(round(spike * 30), 100)
            spike_text = f"APY ökning +{spike*100:.0f}% senaste 7 dagar"

    signals["apy_spike"] = {
        "score": spike_score,
        "signal": "APY Spike",
        "text": spike_text,
        "apy_now": round(apy_now, 2) if apy_now else None,
        "apy_7d_ago": round(apy_7d_ago, 2) if apy_7d_ago else None,
    }

    # ── Signal 3: Reward Collapse ────────────────────────────────────────────
    # Reward APY sjunker snabbt = emissionen tar slut
    reward_score = 0
    reward_text = None
    if reward_now is not None and reward_7d_ago is not None and reward_7d_ago > 1:
        reward_change = (reward_now - reward_7d_ago) / reward_7d_ago
        if reward_change < -0.3:
            reward_score = min(round(abs(reward_change) * 80), 100)
            reward_text = f"Reward APY -{abs(reward_change)*100:.0f}% senaste 7 dagar — emission avtar"
        elif reward_change < -0.5:
            reward_score = 90
            reward_text = f"Reward kollaps: -{abs(reward_change)*100:.0f}% — emission snart slut"

    signals["reward_collapse"] = {
        "score": reward_score,
        "signal": "Reward Kollaps",
        "text": reward_text,
        "reward_now": round(reward_now, 2) if reward_now else None,
        "reward_7d_ago": round(reward_7d_ago, 2) if reward_7d_ago else None,
    }

    # ── Signal 4: Emission Cliff Estimat ────────────────────────────────────
    # Om reward-APY sjunker linjärt, hur många dagar tills den når 0?
    cliff_score = 0
    cliff_text = None
    cliff_days = None
    if reward_now and reward_now > 1 and reward_7d_ago and reward_7d_ago > reward_now:
        daily_decay = (reward_7d_ago - reward_now) / 7
        if daily_decay > 0:
            days_left = reward_now / daily_decay
            cliff_days = round(days_left)
            if days_left < 7:
                cliff_score = 95
                cliff_text = f"Emission-cliff om ~{cliff_days} dagar vid nuvarande avtaktningstakt"
            elif days_left < 14:
                cliff_score = 75
                cliff_text = f"Emission-cliff om ~{cliff_days} dagar"
            elif days_left < 30:
                cliff_score = 45
                cliff_text = f"Emission avtar — cliff estimerat om ~{cliff_days} dagar"

    signals["emission_cliff"] = {
        "score": cliff_score,
        "signal": "Emission Cliff",
        "text": cliff_text,
        "estimated_days_to_cliff": cliff_days,
    }

    # ── Signal 5: Sustainable Base Yield ────────────────────────────────────
    # Base APY stabil över 30 dagar = organisk yield (BRA signal, låg risk)
    sustainable_score = 0
    sustainable_text = None
    if base_now and base_30d_ago and base_30d_ago > 0:
        base_stability = 1 - abs(base_now - base_30d_ago) / base_30d_ago
        if base_stability > 0.8 and base_now > 1:
            sustainable_score = round(base_stability * 100)
            sustainable_text = f"Organisk base APY stabil ({base_30d_ago:.1f}% → {base_now:.1f}%) — hållbar yield"

    signals["sustainable_yield"] = {
        "score": sustainable_score,
        "signal": "Hållbar Yield",
        "text": sustainable_text,
        "base_apy_now": round(base_now, 2) if base_now else None,
        "base_apy_30d_ago": round(base_30d_ago, 2) if base_30d_ago else None,
        "is_positive_signal": True,
    }

    # ── TVL trend (30d) ──────────────────────────────────────────────────────
    tvl_trend_30d = None
    if tvl_now and tvl_30d_ago and tvl_30d_ago > 0:
        tvl_trend_30d = round((tvl_now - tvl_30d_ago) / tvl_30d_ago * 100, 1)

    # ── Composite WOW score ──────────────────────────────────────────────────
    # Högsta enskilda risk-signal dominerar
    risk_scores = [
        signals["tvl_apy_divergence"]["score"],
        signals["apy_spike"]["score"],
        signals["reward_collapse"]["score"],
        signals["emission_cliff"]["score"],
    ]
    wow_score = max(risk_scores)

    # WOW insight text — den starkaste signalen
    wow_text = None
    for sig_key in ["emission_cliff", "tvl_apy_divergence", "reward_collapse", "apy_spike"]:
        if signals[sig_key]["score"] >= 40 and signals[sig_key]["text"]:
            wow_text = signals[sig_key]["text"]
            break

    return {
        "pool_id": pool_id,
        "data_points": len(history),
        "date_range": {
            "from": history[0]["date"] if history else None,
            "to": history[-1]["date"] if history else None,
        },
        "current": {
            "apy": round(apy_now, 2) if apy_now else None,
            "apy_base": round(base_now, 2) if base_now else None,
            "apy_reward": round(reward_now, 2) if reward_now else None,
            "tvl_usd": tvl_now,
        },
        "trends": {
            "tvl_change_7d_pct": signals["tvl_apy_divergence"]["tvl_change_7d"],
            "apy_change_7d_pct": signals["tvl_apy_divergence"]["apy_change_7d"],
            "tvl_change_30d_pct": tvl_trend_30d,
        },
        "wow_score": wow_score,
        "wow_text": wow_text,
        "signals": signals,
    }


def get_global_wow_insights(limit: int = 20) -> dict:
    """
    Hämtar top WOW-insikter globalt — pooler med starkast divergens-signaler.
    Används för zarq.ai/yield-risk startsidan.
    """
    conn = _get_db()
    try:
        # Hämta pooler med historik
        pools_with_history = conn.execute("""
            SELECT DISTINCT h.pool_id, y.project, y.chain, y.symbol, y.tvl_usd, y.apy
            FROM defi_yield_history h
            JOIN defi_yields y ON y.pool_id = h.pool_id
            WHERE y.apy >= 5 AND y.stablecoin = 0
            ORDER BY y.tvl_usd DESC NULLS LAST
            LIMIT 6000
        """).fetchall()

        if not pools_with_history:
            return {"error": "No historical data yet. Run yield_history_crawler.py first.", "insights": []}

        insights = []
        for pool in pools_with_history:
            history = get_pool_history(conn, pool["pool_id"], days=30)
            if len(history) < 7:
                continue
            signals = compute_divergence_signals(pool["pool_id"], history)
            if signals.get("insufficient_data"):
                continue
            if signals["wow_score"] >= 30 and signals["wow_text"]:
                insights.append({
                    "pool_id": pool["pool_id"],
                    "protocol": pool["project"],
                    "chain": pool["chain"],
                    "symbol": pool["symbol"],
                    "tvl_usd": pool["tvl_usd"],
                    "apy": pool["apy"],
                    "wow_score": signals["wow_score"],
                    "wow_text": signals["wow_text"],
                    "trends": signals["trends"],
                    "top_signal": max(signals["signals"].items(), key=lambda x: x[1]["score"])[0],
                })

        insights.sort(key=lambda x: x["wow_score"], reverse=True)

        return {
            "total_analyzed": len(pools_with_history),
            "insights_found": len(insights),
            "insights": insights[:limit],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


def get_pool_full_analysis(pool_id: str) -> dict:
    """
    Full analys av en specifik pool inkl historik + divergens-signaler.
    Används för per-pool detaljsida.
    """
    conn = _get_db()
    try:
        # Pool-metadata
        pool = conn.execute("SELECT * FROM defi_yields WHERE pool_id = ?", (pool_id,)).fetchone()
        if not pool:
            return {"error": f"Pool {pool_id} not found"}

        # Historik 90 dagar
        history_90d = get_pool_history(conn, pool_id, days=90)
        history_30d = [h for h in history_90d if h["date"] >= (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")]

        # Divergens-signaler
        signals = compute_divergence_signals(pool_id, history_90d)

        # Yield Risk Score
        from agentindex.crypto.yield_risk_engine import compute_yield_risk_score, _get_protocol_risk
        risk_level, crash_prob = _get_protocol_risk(conn, pool["project"])
        risk_scoring = compute_yield_risk_score(
            apy=pool["apy"] or 0, apy_base=pool["apy_base"] or 0,
            apy_reward=pool["apy_reward"] or 0, tvl_usd=pool["tvl_usd"],
            il_risk=pool["il_risk"] or "no", stablecoin=pool["stablecoin"] or 0,
            risk_level=risk_level, crash_prob=crash_prob,
        )

        # Sparkline data (last 30 days, daily)
        sparkline_apy = [{"date": h["date"], "apy": h["apy"], "apy_base": h["apy_base"], "apy_reward": h["apy_reward"]} for h in history_30d]
        sparkline_tvl = [{"date": h["date"], "tvl_usd": h["tvl_usd"]} for h in history_30d]

        return {
            "pool_id": pool_id,
            "protocol": pool["project"],
            "chain": pool["chain"],
            "symbol": pool["symbol"],
            "tvl_usd": pool["tvl_usd"],
            "apy": pool["apy"],
            "apy_base": pool["apy_base"],
            "apy_reward": pool["apy_reward"],
            "il_risk": pool["il_risk"],
            "stablecoin": bool(pool["stablecoin"]),
            "protocol_risk_level": risk_level,
            "protocol_crash_prob": round(crash_prob, 3) if crash_prob else None,
            **risk_scoring,
            "divergence": signals,
            "sparkline_apy": sparkline_apy,
            "sparkline_tvl": sparkline_tvl,
            "data_points_90d": len(history_90d),
            "zarq_url": f"https://zarq.ai/yield/pool/{pool_id}",
        }
    finally:
        conn.close()
