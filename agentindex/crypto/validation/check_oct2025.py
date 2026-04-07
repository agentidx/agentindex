import sqlite3
DB = '/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db'
conn = sqlite3.connect(DB)

# What happened around Oct 10, 2025?
tokens = ["bitcoin","ethereum","solana","binancecoin","cardano","ripple","dogecoin","avalanche-2","chainlink","uniswap","aave"]

print("=== PRICE ACTION AROUND OCT 2025 ===")
for window_start, window_end, label in [("2025-10-01","2025-10-20","Oct 1-20"), ("2025-10-05","2025-10-15","Oct 5-15"), ("2025-09-25","2025-10-15","Sep 25-Oct 15")]:
    print(f"\nWindow: {label}")
    print(f"{'Token':>15} | {'Peak':>10} | {'Trough':>10} | {'Drawdown':>10}")
    for tid in tokens:
        r = conn.execute("SELECT MAX(close), MIN(close) FROM crypto_price_history WHERE token_id=? AND date BETWEEN ? AND ?", (tid, window_start, window_end)).fetchone()
        if r and r[0] and r[0] > 0:
            dd = (r[1] - r[0]) / r[0] * 100
            print(f"{tid:>15} | {r[0]:>10.1f} | {r[1]:>10.1f} | {dd:>+9.1f}%")

# BTC daily prices around that period
print("\n=== BTC DAILY PRICES OCT 2025 ===")
for r in conn.execute("SELECT date, close FROM crypto_price_history WHERE token_id='bitcoin' AND date BETWEEN '2025-10-01' AND '2025-10-20' ORDER BY date").fetchall():
    print(f"  {r[0]}: ${r[1]:,.0f}")

conn.close()
