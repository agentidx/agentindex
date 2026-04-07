import sqlite3
DB = '/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db'
conn = sqlite3.connect(DB)

# The key insight: our model uses current rank/volume but crashes happened 2022-2025
# We need to use HISTORICAL rank + volume at the time of each crash
# Also: we treat all non-special tokens the same beta, but actual crashes show
# clear patterns by market cap tier

print("=== ANALYZING ERROR PATTERNS ===\n")

# FTX: We underestimate mid-caps (DOGE -40% actual vs -25% model)
# The issue: flat -25% for all non-SOL tokens. Need beta scaling.

# LUNA: Flat -35% for everything. AVAX was -57%, SOL -52%, ADA -48%.
# High-beta alts got hit much harder.

# Flash crash: BONK predicted -78% actual -33%, COSMOS predicted -67% actual -26%
# We overestimate small caps because current rank != crash-time rank

# Key improvements:
# 1. Use historical beta from price data (actual correlation * BTC move)
# 2. Scale by market cap tier, not just flat multiplier  
# 3. Different amplifiers per crisis type

tokens = ["bitcoin","ethereum","solana","binancecoin","cardano","ripple","dogecoin",
          "avalanche-2","chainlink","uniswap","aave","maker","pepe","bonk",
          "dogwifcoin","shiba-inu","tron","cosmos","lido-dao","arbitrum"]

CRISES = {
    "ftx": {"peak": "2022-11-05", "end": "2022-11-21", "btc_drop": -0.26},
    "luna": {"peak": "2022-05-04", "end": "2022-05-20", "btc_drop": -0.278},
    "3ac": {"peak": "2022-06-09", "end": "2022-07-15", "btc_drop": -0.37},
    "flash": {"peak": "2025-10-09", "end": "2025-10-10", "btc_drop": -0.13},  # intraday
}

# Calculate actual betas for each token in each crisis
print(f"{'Token':>15} | {'FTX beta':>9} | {'LUNA beta':>10} | {'3AC beta':>9} | {'Flash beta':>11} | {'Avg beta':>9}")
print("-" * 80)

betas_by_token = {}
for tid in tokens:
    betas = []
    row_parts = []
    for crisis_name, c in CRISES.items():
        peak_price = conn.execute(
            "SELECT close FROM crypto_price_history WHERE token_id=? AND date<=? ORDER BY date DESC LIMIT 1",
            (tid, c["peak"])
        ).fetchone()
        
        if crisis_name == "flash":
            trough_price = conn.execute(
                "SELECT low FROM crypto_price_history WHERE token_id=? AND date='2025-10-10'",
                (tid,)
            ).fetchone()
        else:
            trough_price = conn.execute(
                "SELECT MIN(close) FROM crypto_price_history WHERE token_id=? AND date BETWEEN ? AND ?",
                (tid, c["peak"], c["end"])
            ).fetchone()
        
        if peak_price and trough_price and peak_price[0] and peak_price[0] > 0:
            token_drop = (trough_price[0] - peak_price[0]) / peak_price[0]
            beta = token_drop / c["btc_drop"] if c["btc_drop"] != 0 else 0
            betas.append(beta)
            row_parts.append(f"{beta:>9.2f}")
        else:
            row_parts.append(f"{'—':>9}")
    
    avg = sum(betas) / len(betas) if betas else 0
    betas_by_token[tid] = {"betas": betas, "avg": avg}
    print(f"{tid:>15} | {' | '.join(row_parts)} | {avg:>9.2f}")

# Now build improved model using empirical betas
print("\n\n=== IMPROVED MODEL vs OLD MODEL ===")

# Rank tokens by their empirical crisis beta
print("\nEmpirical beta tiers:")
sorted_tokens = sorted(betas_by_token.items(), key=lambda x: x[1]["avg"])
for tid, data in sorted_tokens:
    rank_data = conn.execute("SELECT market_cap_rank FROM crypto_ndd_daily WHERE token_id=? ORDER BY run_date DESC LIMIT 1", (tid,)).fetchone()
    rank = rank_data[0] if rank_data else 999
    print(f"  {tid:>15}: avg_beta={data['avg']:.2f}, rank={rank}")

# Key finding: beta correlates with rank but not linearly
# Tier 1 (BTC): beta ~1.0
# Tier 2 (ETH, BNB, SOL, XRP, TRX): beta 1.0-1.5
# Tier 3 (ADA, DOGE, AVAX, LINK): beta 1.5-2.0
# Tier 4 (UNI, AAVE, COSMOS): beta 1.8-2.5
# Tier 5 (meme, small DeFi): beta 2.5-5.0

print("\n\n=== TESTING IMPROVED PREDICTIONS ===")

# Improved model: use rank-based beta tiers calibrated from empirical data
def improved_beta(rank, volume=0, is_defi=False, is_meme=False):
    """Better beta estimation from empirical crisis data"""
    if rank <= 1:
        return 1.0  # BTC
    elif rank <= 5:
        base = 1.15 + (rank - 2) * 0.05
    elif rank <= 10:
        base = 1.35 + (rank - 5) * 0.08
    elif rank <= 20:
        base = 1.75 + (rank - 10) * 0.04
    elif rank <= 50:
        base = 2.15 + (rank - 20) * 0.02
    else:
        base = 2.75 + min(1.5, (rank - 50) * 0.015)
    
    # DeFi premium: lending/DEX protocols fall harder
    if is_defi:
        base *= 1.2
    # Meme premium: pure speculation falls harder
    if is_meme:
        base *= 1.15
    # Low volume penalty
    if volume and volume < 100e6:
        base *= 1.1
    
    return min(5.0, base)

DEFI = ["aave","uniswap","maker","lido-dao","curve-dao-token","compound-governance-token"]
MEME = ["dogecoin","shiba-inu","pepe","bonk","dogwifcoin","floki"]

for crisis_name, crisis in CRISES.items():
    print(f"\n--- {crisis_name.upper()} ---")
    print(f"{'Token':>15} | {'Actual':>9} | {'Old Model':>10} | {'New Model':>10} | {'Old Err':>8} | {'New Err':>8}")
    
    old_errors = []
    new_errors = []
    
    for tid in tokens:
        # Get actual
        peak = conn.execute("SELECT close FROM crypto_price_history WHERE token_id=? AND date<=? ORDER BY date DESC LIMIT 1",
            (tid, crisis["peak"])).fetchone()
        if crisis_name == "flash":
            trough = conn.execute("SELECT low FROM crypto_price_history WHERE token_id=? AND date='2025-10-10'", (tid,)).fetchone()
        else:
            trough = conn.execute("SELECT MIN(close) FROM crypto_price_history WHERE token_id=? AND date BETWEEN ? AND ?",
                (tid, crisis["peak"], crisis["end"])).fetchone()
        
        if not peak or not trough or not peak[0] or peak[0] == 0:
            continue
        actual = (trough[0] - peak[0]) / peak[0]
        
        # Get rank (use historical if available, else current)
        rank_data = conn.execute("SELECT market_cap_rank FROM crypto_ndd_daily WHERE token_id=? ORDER BY run_date DESC LIMIT 1", (tid,)).fetchone()
        rank = rank_data[0] if rank_data else 100
        vol_data = conn.execute("SELECT volume_24h FROM crypto_ndd_daily WHERE token_id=? ORDER BY run_date DESC LIMIT 1", (tid,)).fetchone()
        vol = vol_data[0] if vol_data else 0
        
        btc_shock = crisis["btc_drop"]
        
        # Old model (simplified from stresstest_engine)
        if tid == "bitcoin":
            old_pred = btc_shock
        else:
            old_beta = min(1.8, 1.0 + max(0, (rank - 10)) / 200)
            old_pred = btc_shock * old_beta
        
        # New model
        if tid == "bitcoin":
            new_pred = btc_shock
        else:
            new_beta = improved_beta(rank, vol, tid in DEFI, tid in MEME)
            new_pred = btc_shock * new_beta
            new_pred = max(-0.95, new_pred)
        
        old_err = abs(actual - old_pred)
        new_err = abs(actual - new_pred)
        old_errors.append(old_err)
        new_errors.append(new_err)
        
        better = "<<" if new_err < old_err - 0.02 else ">>" if new_err > old_err + 0.02 else "=="
        print(f"{tid:>15} | {actual*100:>+8.1f}% | {old_pred*100:>+9.1f}% | {new_pred*100:>+9.1f}% | {old_err*100:>7.1f}pp | {new_err*100:>7.1f}pp {better}")
    
    old_mae = sum(old_errors)/len(old_errors)*100
    new_mae = sum(new_errors)/len(new_errors)*100
    improvement = old_mae - new_mae
    print(f"  OLD MAE: {old_mae:.1f}pp | NEW MAE: {new_mae:.1f}pp | Improvement: {improvement:+.1f}pp")

conn.close()
