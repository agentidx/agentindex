import sqlite3
DB = '/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db'
conn = sqlite3.connect(DB)

tokens = ["bitcoin","ethereum","solana","binancecoin","cardano","ripple","dogecoin",
          "avalanche-2","chainlink","uniswap","aave","maker","pepe","bonk",
          "dogwifcoin","shiba-inu","tron","cosmos","lido-dao","arbitrum"]

print("=== FLASH CRASH OCT 10, 2025 ===")
print("Comparing Oct 9 close vs Oct 10 low (intraday crash)")
print(f"{'Token':>15} | {'Oct 9 Close':>12} | {'Oct 10 Low':>12} | {'Oct 10 Close':>12} | {'Flash DD':>10} | {'Recovery':>10}")
print("-" * 90)

for tid in tokens:
    # Oct 9 close = pre-crash
    r9 = conn.execute("SELECT close FROM crypto_price_history WHERE token_id=? AND date='2025-10-09'", (tid,)).fetchone()
    # Oct 10 OHLC
    r10 = conn.execute("SELECT open, high, low, close FROM crypto_price_history WHERE token_id=? AND date='2025-10-10'", (tid,)).fetchone()
    if not r9 or not r10:
        continue
    
    pre = r9[0]
    low = r10[2]
    close = r10[3]
    
    if pre and pre > 0 and low:
        flash_dd = (low - pre) / pre * 100
        close_dd = (close - pre) / pre * 100
        recovery = close_dd - flash_dd  # how much bounced back
        print(f"{tid:>15} | {pre:>12.2f} | {low:>12.2f} | {close:>12.2f} | {flash_dd:>+9.1f}% | {recovery:>+9.1f}%")

# Also check Oct 10 volume spike
print("\n=== VOLUME SPIKE OCT 10 vs average ===")
for tid in ["bitcoin","ethereum","solana","dogecoin","avalanche-2"]:
    avg = conn.execute("SELECT AVG(volume) FROM crypto_price_history WHERE token_id=? AND date BETWEEN '2025-09-25' AND '2025-10-09'", (tid,)).fetchone()
    vol10 = conn.execute("SELECT volume FROM crypto_price_history WHERE token_id=? AND date='2025-10-10'", (tid,)).fetchone()
    if avg and avg[0] and vol10 and vol10[0]:
        ratio = vol10[0] / avg[0]
        print(f"{tid:>15} | Avg vol: {avg[0]:>15,.0f} | Oct 10: {vol10[0]:>15,.0f} | {ratio:.1f}x")

conn.close()
