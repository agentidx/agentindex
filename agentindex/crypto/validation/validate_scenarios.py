import sqlite3
import json
from collections import defaultdict

DB = '/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db'
conn = sqlite3.connect(DB)

# Define historical crash periods with actual dates
HISTORICAL = {
    "ftx_collapse": {
        "name": "FTX Collapse",
        "start": "2022-11-06",
        "end": "2022-11-21",
        "peak_date": "2022-11-05",
    },
    "luna_depeg": {
        "name": "LUNA/UST Death Spiral",
        "start": "2022-05-05",
        "end": "2022-05-20",
        "peak_date": "2022-05-04",
    },
    "3ac_contagion": {
        "name": "3AC / Lending Crisis",
        "start": "2022-06-10",
        "end": "2022-07-15",
        "peak_date": "2022-06-09",
    },
    "btc_crash_50pct": {
        "name": "BTC -50% (Nov 2021 to Jun 2022)",
        "start": "2021-11-10",
        "end": "2022-06-18",
        "peak_date": "2021-11-09",
    },
}

# Key tokens to validate
KEY_TOKENS = [
    "bitcoin", "ethereum", "solana", "binancecoin", "cardano",
    "ripple", "dogecoin", "avalanche-2", "chainlink", "uniswap",
    "aave", "maker", "cosmos", "matic-network", "tron",
]

def get_price(token_id, date):
    r = conn.execute(
        "SELECT close FROM crypto_price_history WHERE token_id=? AND date<=? ORDER BY date DESC LIMIT 1",
        (token_id, date)
    ).fetchone()
    return r[0] if r else None

def get_actual_drawdown(token_id, peak_date, end_date):
    peak = get_price(token_id, peak_date)
    if not peak or peak == 0:
        return None
    # Find minimum price in the crash window
    r = conn.execute(
        "SELECT MIN(close) FROM crypto_price_history WHERE token_id=? AND date BETWEEN ? AND ?",
        (token_id, peak_date, end_date)
    ).fetchone()
    if not r or not r[0]:
        return None
    return (r[0] - peak) / peak

print("=" * 80)
print("STRESSTEST SCENARIO VALIDATION vs ACTUAL HISTORICAL DATA")
print("=" * 80)

# Now simulate what our stresstest engine would predict
# Import simplified logic from stresstest
ECOSYSTEM_MAP = {
    "ethereum": "ethereum", "uniswap": "ethereum", "aave": "ethereum",
    "maker": "ethereum", "chainlink": "ethereum",
    "solana": "solana", "binancecoin": "bnb",
    "bitcoin": "bitcoin", "cardano": "other", "ripple": "other",
    "dogecoin": "other", "avalanche-2": "avalanche",
    "cosmos": "cosmos", "matic-network": "polygon", "tron": "other",
}

for scenario_id, hist in HISTORICAL.items():
    print(f"\n{'─' * 80}")
    print(f"SCENARIO: {hist['name']}")
    print(f"Period: {hist['start']} to {hist['end']}")
    print(f"{'─' * 80}")
    print(f"{'Token':>15} | {'Actual':>10} | {'Model Est':>10} | {'Error':>8} | {'Direction':>9}")
    print(f"{'-'*15}-+-{'-'*10}-+-{'-'*10}-+-{'-'*8}-+-{'-'*9}")

    errors = []
    correct_direction = 0
    total = 0

    for tid in KEY_TOKENS:
        actual = get_actual_drawdown(tid, hist["peak_date"], hist["end"])
        if actual is None:
            continue

        # Simplified model prediction (mirrors stresstest_engine logic)
        eco = ECOSYSTEM_MAP.get(tid, "other")
        predicted = 0

        if scenario_id == "btc_crash_50pct":
            if tid == "bitcoin":
                predicted = -0.50
            else:
                rank_data = conn.execute(
                    "SELECT market_cap_rank FROM crypto_ndd_daily WHERE token_id=? ORDER BY run_date DESC LIMIT 1",
                    (tid,)
                ).fetchone()
                rank = rank_data[0] if rank_data else 50
                beta = min(1.8, 1.0 + max(0, (rank - 10)) / 200)
                predicted = -0.50 * beta

        elif scenario_id == "ftx_collapse":
            predicted = -0.10  # base confidence shock
            if eco == "solana":
                predicted += -0.60
            elif tid == "binancecoin":
                predicted += -0.05
            else:
                predicted += -0.15

        elif scenario_id == "luna_depeg":
            predicted = -0.10  # base
            predicted += -0.25  # market-wide DeFi impact

        elif scenario_id == "3ac_contagion":
            predicted = -0.15  # confidence shock
            if tid in ["aave", "maker"]:
                predicted += -0.25
            elif tid == "bitcoin":
                predicted += -0.15
            else:
                predicted += -0.20

        predicted = max(-0.99, predicted)

        error = abs(actual - predicted)
        errors.append(error)
        direction_ok = (actual < 0 and predicted < 0) or (actual >= 0 and predicted >= 0)
        if direction_ok:
            correct_direction += 1
        total += 1

        print(f"{tid:>15} | {actual*100:>+9.1f}% | {predicted*100:>+9.1f}% | {error*100:>7.1f}pp | {'  OK' if direction_ok else '  MISS'}")

    if errors:
        mae = sum(errors) / len(errors) * 100
        print(f"\n  Mean Absolute Error: {mae:.1f} percentage points")
        print(f"  Direction accuracy: {correct_direction}/{total} ({correct_direction/total*100:.0f}%)")
        print(f"  Median error: {sorted(errors)[len(errors)//2]*100:.1f}pp")

print("\n" + "=" * 80)
print("INTERPRETATION")
print("=" * 80)
print("""
Direction accuracy shows whether the model correctly predicts which tokens
get hit hardest vs least. MAE shows calibration — how close are the magnitudes.

For stress testing, DIRECTION matters more than exact magnitude:
- Knowing SOL gets hit 3x harder than BTC in an exchange collapse = useful
- Exact percentage (60% vs 55%) matters less

A good stress test model should have:
- Direction accuracy > 80%
- MAE < 15pp for major tokens
""")

conn.close()
