import sqlite3
conn = sqlite3.connect('/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db')

r = conn.execute('SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT token_id) FROM crypto_price_history').fetchone()
print(f'Price history: {r[0]} to {r[1]}, {r[2]} rows, {r[3]} tokens')

for period, label in [('2022-11-01','FTX'), ('2022-05-01','LUNA'), ('2022-06-01','3AC'), ('2020-03-01','COVID')]:
    r = conn.execute("SELECT COUNT(DISTINCT token_id) FROM crypto_price_history WHERE date >= ? AND date <= date(?, '+30 days')", (period, period)).fetchone()
    print(f'{label} ({period}): {r[0]} tokens with data')

r = conn.execute('SELECT MIN(date), MAX(date), MIN(close), MAX(close) FROM crypto_price_history WHERE token_id="bitcoin"').fetchone()
print(f'BTC: {r[0]} to {r[1]}, low {r[2]}, high {r[3]}')

r = conn.execute("SELECT date, close FROM crypto_price_history WHERE token_id='bitcoin' ORDER BY date LIMIT 3").fetchall()
print(f'First BTC: {list(r)}')

r = conn.execute("SELECT date, close FROM crypto_price_history WHERE token_id='bitcoin' ORDER BY date DESC LIMIT 3").fetchall()
print(f'Last BTC: {list(r)}')

conn.close()
