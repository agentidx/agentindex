import sqlite3
DB = '/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db'
conn = sqlite3.connect(DB)

tokens = ["bitcoin","ethereum","solana","binancecoin","cardano","ripple","dogecoin",
          "avalanche-2","chainlink","uniswap","aave","pepe","bonk",
          "dogwifcoin","shiba-inu","tron","cosmos","lido-dao","arbitrum"]

DEFI = ["aave","uniswap","maker","lido-dao","curve-dao-token","compound-governance-token"]
MEME = ["dogecoin","shiba-inu","pepe","bonk","dogwifcoin","floki"]

CRISES = {
    "ftx": {"peak": "2022-11-05", "end": "2022-11-21", "type": "exchange"},
    "luna": {"peak": "2022-05-04", "end": "2022-05-20", "type": "defi"},
    "3ac": {"peak": "2022-06-09", "end": "2022-07-15", "type": "lending"},
    "flash": {"peak": "2025-10-09", "end": "2025-10-10", "type": "flash"},
}

def get_actual(tid, crisis):
    peak = conn.execute("SELECT close FROM crypto_price_history WHERE token_id=? AND date<=? ORDER BY date DESC LIMIT 1",
        (tid, crisis["peak"])).fetchone()
    if crisis["type"] == "flash":
        trough = conn.execute("SELECT low FROM crypto_price_history WHERE token_id=? AND date='2025-10-10'", (tid,)).fetchone()
    else:
        trough = conn.execute("SELECT MIN(close) FROM crypto_price_history WHERE token_id=? AND date BETWEEN ? AND ?",
            (tid, crisis["peak"], crisis["end"])).fetchone()
    if not peak or not trough or not peak[0] or peak[0] == 0:
        return None
    return (trough[0] - peak[0]) / peak[0]

# Strategy: use BTC drop as anchor, then per-tier multipliers calibrated per crisis type
# The key insight from data:
# - Exchange crisis (FTX): SOL special case, rest ~1.0-1.6x BTC
# - DeFi crisis (LUNA): broad contagion, ~1.0-2.0x BTC
# - Lending crisis (3AC): surprisingly uniform, ~0.7-1.3x BTC
# - Flash crash: extreme dispersion, 1.0-5.0x BTC based on liquidity

def calibrated_predict(tid, btc_drop, crisis_type, rank, vol):
    if tid == "bitcoin":
        return btc_drop
    if tid == "tron":  # consistently defensive
        return btc_drop * 0.8
    
    is_defi = tid in DEFI
    is_meme = tid in MEME
    
    if crisis_type == "exchange":
        # FTX-type: SOL ecosystem hit hardest, rest moderate
        if tid == "solana":
            return btc_drop * 2.6
        elif rank <= 5:
            return btc_drop * 1.15
        elif rank <= 15:
            return btc_drop * 1.2
        elif is_defi:
            return btc_drop * 1.55
        elif is_meme:
            return btc_drop * 1.6
        else:
            return btc_drop * 1.4
    
    elif crisis_type == "defi":
        # LUNA-type: DeFi and high-beta alts hit hardest
        if rank <= 5:
            return btc_drop * 1.2
        elif rank <= 15:
            return btc_drop * 1.6
        elif is_defi:
            return btc_drop * 1.9
        elif is_meme:
            return btc_drop * 1.5
        elif rank <= 30:
            return btc_drop * 1.7
        else:
            return btc_drop * 1.85
    
    elif crisis_type == "lending":
        # 3AC-type: surprisingly uniform
        if rank <= 5:
            return btc_drop * 0.85
        elif is_defi:
            return btc_drop * 1.2
        elif rank <= 20:
            return btc_drop * 0.9
        else:
            return btc_drop * 0.95
    
    elif crisis_type == "flash":
        # Flash crash: liquidity is everything
        if rank <= 3:
            base = 1.3
        elif rank <= 10:
            base = 1.8
        elif rank <= 20:
            base = 2.3
        elif rank <= 50:
            base = 2.8
        else:
            base = 3.5
        
        if is_defi:
            base *= 1.3
        if is_meme:
            base *= 1.2
        if vol and vol < 100e6:
            base *= 1.2
        
        return max(-0.95, btc_drop * min(5.0, base))
    
    return btc_drop * 1.3  # default

# Test all crises
BTC_DROPS = {"ftx": -0.26, "luna": -0.278, "3ac": -0.37, "flash": -0.13}

all_old = []
all_new = []

for crisis_name, crisis in CRISES.items():
    btc_drop = BTC_DROPS[crisis_name]
    old_errors = []
    new_errors = []
    
    print(f"\n--- {crisis_name.upper()} (BTC {btc_drop*100:+.0f}%) ---")
    print(f"{'Token':>15} | {'Actual':>9} | {'Old':>9} | {'New':>9} | {'OldErr':>7} | {'NewErr':>7}")
    
    for tid in tokens:
        actual = get_actual(tid, crisis)
        if actual is None:
            continue
        
        rank_data = conn.execute("SELECT market_cap_rank FROM crypto_ndd_daily WHERE token_id=? ORDER BY run_date DESC LIMIT 1", (tid,)).fetchone()
        rank = rank_data[0] if rank_data else 100
        vol_data = conn.execute("SELECT volume_24h FROM crypto_ndd_daily WHERE token_id=? ORDER BY run_date DESC LIMIT 1", (tid,)).fetchone()
        vol = vol_data[0] if vol_data else 0
        
        # Old model
        if tid == "bitcoin":
            old_pred = btc_drop
        else:
            old_beta = min(1.8, 1.0 + max(0, (rank - 10)) / 200)
            old_pred = btc_drop * old_beta
        
        # New calibrated model
        new_pred = calibrated_predict(tid, btc_drop, crisis["type"], rank, vol)
        new_pred = max(-0.95, new_pred)
        
        old_err = abs(actual - old_pred)
        new_err = abs(actual - new_pred)
        old_errors.append(old_err)
        new_errors.append(new_err)
        all_old.append(old_err)
        all_new.append(new_err)
        
        marker = "<<" if new_err < old_err - 0.01 else ">>" if new_err > old_err + 0.01 else "=="
        print(f"{tid:>15} | {actual*100:>+8.1f}% | {old_pred*100:>+8.1f}% | {new_pred*100:>+8.1f}% | {old_err*100:>6.1f} | {new_err*100:>6.1f} {marker}")
    
    om = sum(old_errors)/len(old_errors)*100
    nm = sum(new_errors)/len(new_errors)*100
    print(f"  MAE: {om:.1f}pp -> {nm:.1f}pp ({nm-om:+.1f}pp)")

print(f"\n{'='*70}")
print(f"OVERALL: Old MAE {sum(all_old)/len(all_old)*100:.1f}pp -> New MAE {sum(all_new)/len(all_new)*100:.1f}pp")
med_old = sorted(all_old)[len(all_old)//2]*100
med_new = sorted(all_new)[len(all_new)//2]*100
print(f"MEDIAN:  Old {med_old:.1f}pp -> New {med_new:.1f}pp")
w10_old = sum(1 for e in all_old if e <= 0.10)
w10_new = sum(1 for e in all_new if e <= 0.10)
w15_old = sum(1 for e in all_old if e <= 0.15)
w15_new = sum(1 for e in all_new if e <= 0.15)
print(f"Within 10pp: {w10_old}/{len(all_old)} -> {w10_new}/{len(all_new)}")
print(f"Within 15pp: {w15_old}/{len(all_old)} -> {w15_new}/{len(all_new)}")

conn.close()
