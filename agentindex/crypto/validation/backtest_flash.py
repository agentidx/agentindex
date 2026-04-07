import sqlite3
DB = '/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db'
conn = sqlite3.connect(DB)

tokens = ["bitcoin","ethereum","solana","binancecoin","cardano","ripple","dogecoin",
          "avalanche-2","chainlink","uniswap","aave","maker","pepe","bonk",
          "dogwifcoin","shiba-inu","tron","cosmos","lido-dao","arbitrum"]

ECOSYSTEM = {
    "ethereum":"ethereum","uniswap":"ethereum","aave":"ethereum","chainlink":"ethereum",
    "maker":"ethereum","lido-dao":"ethereum",
    "solana":"solana","bonk":"solana","dogwifcoin":"solana",
    "binancecoin":"bnb","bitcoin":"bitcoin",
    "cardano":"other","ripple":"other","dogecoin":"other","tron":"other",
    "avalanche-2":"avalanche","cosmos":"cosmos","shiba-inu":"ethereum",
    "pepe":"ethereum","arbitrum":"arbitrum",
}

MEME = ["dogecoin","shiba-inu","pepe","bonk","dogwifcoin","floki"]
DEFI = ["aave","uniswap","maker","curve-dao-token","lido-dao","compound-governance-token"]

print("=" * 90)
print("FLASH CRASH OCT 10, 2025 — MODEL vs ACTUAL (Intraday Peak-to-Trough)")
print("=" * 90)
print(f"{'Token':>15} | {'Actual':>10} | {'Model':>10} | {'Error':>8} | {'Dir':>5} | {'Notes'}")
print("-" * 90)

errors = []
correct = 0
total = 0

for tid in tokens:
    # Actual: Oct 9 close vs Oct 10 intraday low
    r9 = conn.execute("SELECT close FROM crypto_price_history WHERE token_id=? AND date='2025-10-09'", (tid,)).fetchone()
    r10 = conn.execute("SELECT low FROM crypto_price_history WHERE token_id=? AND date='2025-10-10'", (tid,)).fetchone()
    if not r9 or not r10 or not r9[0] or r9[0] == 0:
        continue
    actual = (r10[0] - r9[0]) / r9[0]

    # Model prediction (mirrors stresstest_engine flash crash logic)
    eco = ECOSYSTEM.get(tid, "other")
    rank_data = conn.execute("SELECT market_cap_rank FROM crypto_ndd_daily WHERE token_id=? ORDER BY run_date DESC LIMIT 1", (tid,)).fetchone()
    rank = rank_data[0] if rank_data else 100
    vol_data = conn.execute("SELECT volume_24h FROM crypto_ndd_daily WHERE token_id=? ORDER BY run_date DESC LIMIT 1", (tid,)).fetchone()
    vol = vol_data[0] if vol_data else 0

    if tid == "bitcoin":
        predicted = -0.13
    elif eco == "stablecoin":
        predicted = -0.02
    else:
        beta = min(3.5, 1.0 + max(0, (rank - 5)) / 30)
        predicted = -0.13 * beta
        # Low liquidity
        if vol and vol < 50e6:
            predicted += -0.25
        elif vol and vol < 200e6:
            predicted += -0.125
        # DeFi extra
        if tid in DEFI:
            predicted += -0.15
        # Meme extra
        if tid in MEME:
            predicted += -0.20

    predicted = max(-0.99, predicted)
    error = abs(actual - predicted)
    errors.append(error)
    dir_ok = (actual < 0 and predicted < 0)
    if dir_ok:
        correct += 1
    total += 1

    notes = ""
    if tid in MEME: notes = "meme"
    elif tid in DEFI: notes = "defi"
    elif rank and rank <= 10: notes = "top10"
    else: notes = f"rank {rank}"

    print(f"{tid:>15} | {actual*100:>+9.1f}% | {predicted*100:>+9.1f}% | {error*100:>7.1f}pp | {'  OK' if dir_ok else 'MISS'} | {notes}")

mae = sum(errors)/len(errors)*100
median = sorted(errors)[len(errors)//2]*100

print(f"\n{'=' * 90}")
print(f"RESULTS: {total} tokens tested")
print(f"  Direction accuracy: {correct}/{total} ({correct/total*100:.0f}%)")
print(f"  Mean Absolute Error: {mae:.1f}pp")
print(f"  Median Error: {median:.1f}pp")
print(f"  Tokens within 10pp: {sum(1 for e in errors if e < 0.10)}/{total}")
print(f"  Tokens within 15pp: {sum(1 for e in errors if e < 0.15)}/{total}")
print(f"  Worst miss: {max(errors)*100:.1f}pp")

conn.close()
