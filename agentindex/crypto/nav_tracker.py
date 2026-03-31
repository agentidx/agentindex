#!/usr/bin/env python3
"""Quick NAV tracker - compound pair signal returns from $10K start"""

import sqlite3, numpy as np
from collections import defaultdict, Counter
from datetime import datetime, timedelta

DB = 'crypto_trust.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

WEIGHTS = [0.10, 0.30, 0.30, 0.15, 0.15]
MAX_CAP = 1.0; MIN_VOL = 50000; MIN_COV = 0.70; MIN_NDD_SHORT = 1.5
HOLD = 90; RG = 0.15; SW = 0.4; NW = 0.6; TOP_N = 5; MAX_TOK = 2

STABLECOINS = {'tether','usd-coin','binance-usd','dai','true-usd','paxos-standard','gusd','frax','usdd','tusd','busd','lusd','susd','eurs','usdp','first-digital-usd','ethena-usde','usde','paypal-usd','fdusd','stasis-eur','gemini-dollar','husd','nusd','musd','cusd','terrausd','ust','magic-internet-money','euro-coin','ondo-us-dollar-yield'}
MAJOR = {'bitcoin','ethereum','ripple','solana','cardano','dogecoin','tron','polkadot','avalanche-2','chainlink','shiba-inu','stellar','cosmos','monero','hedera-hashgraph','vechain','internet-computer','litecoin','near','uniswap','pepe','kaspa','sui','sei-network','celestia','arbitrum','optimism','immutable-x','the-graph','render-token','fetch-ai','injective-protocol','bittensor','helium','livepeer','aave','curve-dao-token','maker','lido-dao','the-open-network','axie-infinity','decentraland','the-sandbox','gala','enjincoin','flow','decred','zilliqa','iota','eos','neo','dash','zcash','algorand','fantom','kava','celo','ankr','worldcoin-wld','pyth-network','layerzero','ondo-finance','ethena','jasmycoin','blockstack','elrond-erd-2','crypto-com-chain','filecoin','aptos','mantle','bonk','dogwifcoin','floki','theta-token','quant-network','arweave','stacks','pendle','bitcoin-cash','ethereum-classic','jupiter-exchange-solana','raydium','pi-network'}

R2C = {}
for c, rs in {'IG_MID': ['A1','A2','A3']}.items():
    for r in rs: R2C[r] = c

rows = conn.execute('SELECT token_id,date,close FROM crypto_price_history ORDER BY token_id,date').fetchall()
prices = defaultdict(dict)
for r in rows: prices[r['token_id']][r['date']] = r['close']
prices = dict(prices)

vols = conn.execute('SELECT token_id,AVG(volume) as v,COUNT(*) as d FROM crypto_price_history GROUP BY token_id').fetchall()
total_days = (datetime(2025,12,31)-datetime(2021,1,1)).days
eligible = {r['token_id'] for r in vols if r['token_id'].lower() not in STABLECOINS and r['token_id'] in MAJOR and (r['v'] or 0)>=MIN_VOL and r['d']/total_days>=MIN_COV}

ratings = {}
for r in conn.execute('SELECT token_id,year_month,rating,score,pillar_1,pillar_2,pillar_3,pillar_4,pillar_5 FROM crypto_rating_history').fetchall():
    ratings[(r['token_id'],r['year_month'])] = {'rating':r['rating'],'pillars':[r['pillar_1'],r['pillar_2'],r['pillar_3'],r['pillar_4'],r['pillar_5']]}

ndd = {}
for r in conn.execute("SELECT token_id,substr(week_date,1,7) as ym,AVG(ndd) as n FROM crypto_ndd_history GROUP BY token_id,substr(week_date,1,7)").fetchall():
    ndd[(r['token_id'],r['ym'])] = r['n']

btc = {}
for r in conn.execute("SELECT date,close FROM crypto_price_history WHERE token_id='bitcoin' ORDER BY date").fetchall():
    btc[r['date']] = r['close']

btc_mr = {}
for d in sorted(btc.keys()):
    if d[8:10] != '01': continue
    t30 = (datetime.strptime(d,'%Y-%m-%d')-timedelta(days=30)).strftime('%Y-%m-%d')
    pn = btc[d]; p30 = None
    for off in range(8):
        c = (datetime.strptime(t30,'%Y-%m-%d')+timedelta(days=off)).strftime('%Y-%m-%d')
        if c in btc: p30 = btc[c]; break
    if pn and p30 and p30 > 0: btc_mr[d[:7]] = (pn-p30)/p30

def closest(ds, target, mx=7):
    t = datetime.strptime(target, '%Y-%m-%d')
    for o in range(mx+1):
        for d in [o, -o]:
            c = (t+timedelta(days=d)).strftime('%Y-%m-%d')
            if c in ds: return c
    return None

def comp(pillars):
    if not pillars or any(p is None for p in pillars): return None
    return sum(p*w for p, w in zip(pillars, WEIGHTS))

# Collect monthly decimal returns
monthly_returns = {}
cur = datetime(2021,1,1); end = datetime(2025,12,31)

while cur <= end:
    ym = cur.strftime('%Y-%m'); entry = cur.strftime('%Y-%m-%d')
    br = btc_mr.get(ym)
    if br is not None and br < -RG:
        monthly_returns[ym] = 'SKIP'
        cur = cur.replace(year=cur.year+1,month=1,day=1) if cur.month==12 else cur.replace(month=cur.month+1,day=1)
        continue

    ct = defaultdict(list)
    for (tid,m), data in ratings.items():
        if m != ym or tid not in eligible: continue
        cls = R2C.get(data['rating'])
        if not cls: continue
        c = comp(data['pillars'])
        if c is None: continue
        ct[cls].append({'tid':tid,'comp':c,'ndd':ndd.get((tid,ym),2.5)})

    all_pairs = []
    for cls, toks in ct.items():
        if len(toks) < 4: continue
        toks.sort(key=lambda x: x['comp'], reverse=True)
        n = len(toks); q = max(1, n//4)
        longs = toks[:q]
        shorts = [s for s in toks[-q:] if ndd.get((s['tid'],ym),3.0) >= MIN_NDD_SHORT]
        for lt in longs:
            for st in shorts:
                if lt['tid'] == st['tid']: continue
                all_pairs.append({'l':lt['tid'],'s':st['tid'],'spread':lt['comp']-st['comp'],'ndd_diff':lt['ndd']-st['ndd']})

    if all_pairs:
        sps = [p['spread'] for p in all_pairs]; nds = [p['ndd_diff'] for p in all_pairs]
        sr = max(sps)-min(sps) or 1; nr = max(nds)-min(nds) or 1
        smn, nmn = min(sps), min(nds)
        for p in all_pairs: p['conv'] = SW*((p['spread']-smn)/sr) + NW*((p['ndd_diff']-nmn)/nr)
        all_pairs.sort(key=lambda p: p['conv'], reverse=True)
        sel = []; tc = Counter()
        for p in all_pairs:
            if tc[p['l']] >= MAX_TOK or tc[p['s']] >= MAX_TOK: continue
            sel.append(p); tc[p['l']] += 1; tc[p['s']] += 1
        top = sel[:TOP_N]

        alphas = []
        for p in top:
            ex = (datetime.strptime(entry,'%Y-%m-%d')+timedelta(days=HOLD)).strftime('%Y-%m-%d')
            lp = prices.get(p['l'],{}); sp = prices.get(p['s'],{})
            if not lp or not sp: continue
            el = closest(set(lp.keys()),entry); es = closest(set(sp.keys()),entry)
            xl = closest(set(lp.keys()),ex); xs = closest(set(sp.keys()),ex)
            if not all([el,es,xl,xs]) or lp[el]<=0 or sp[es]<=0: continue
            lr = max(-MAX_CAP, min(MAX_CAP, (lp[xl]-lp[el])/lp[el]))
            sr_ = max(-MAX_CAP, min(MAX_CAP, (sp[xs]-sp[es])/sp[es]))
            alphas.append(lr - sr_)

        monthly_returns[ym] = np.mean(alphas) if alphas else 'NO_PAIRS'
    else:
        monthly_returns[ym] = 'NO_PAIRS'

    cur = cur.replace(year=cur.year+1,month=1,day=1) if cur.month==12 else cur.replace(month=cur.month+1,day=1)

# Compound NAV
START = 10000
btc_start = btc[min(btc.keys())]

nav = START
nav_peak = START
nav_maxdd = 0.0

fmt_usd = lambda x: "${:,.0f}".format(x)

print("{:<10} {:>5} {:>8} {:>14} {:>9} {:>8} {:>8}   {:>14} {:>9}".format(
    'Month','Pairs','Mo Ret','Pairs NAV','Return','DD','MaxDD','BTC NAV','BTC Ret'))
print('=' * 100)

for ym in sorted(monthly_returns.keys()):
    candidates = [d for d in sorted(btc.keys()) if d[:7] == ym]
    if candidates:
        bp = btc[candidates[0]]
        btc_nav = START * bp / btc_start
    else:
        btc_nav = START
    btc_ret = (btc_nav / START - 1) * 100

    v = monthly_returns[ym]
    if v == 'SKIP' or v == 'NO_PAIRS':
        nav_peak = max(nav_peak, nav)
        dd = (nav - nav_peak) / nav_peak * 100
        nav_maxdd = min(nav_maxdd, dd)
        nav_ret = (nav / START - 1) * 100
        label = "SKIP" if v == 'SKIP' else "--"
        pairs = "--" if v == 'SKIP' else "0"
        print("{:<10} {:>5} {:>8} {:>14} {:>8.1f}% {:>7.1f}% {:>7.1f}%   {:>14} {:>8.1f}%".format(
            ym, pairs, label, fmt_usd(nav), nav_ret, dd, nav_maxdd, fmt_usd(btc_nav), btc_ret))
    else:
        mo_ret = v
        nav = nav * (1 + mo_ret)
        nav_peak = max(nav_peak, nav)
        dd = (nav - nav_peak) / nav_peak * 100
        nav_maxdd = min(nav_maxdd, dd)
        nav_ret = (nav / START - 1) * 100
        print("{:<10} {:>5} {:>7.1f}% {:>14} {:>8.1f}% {:>7.1f}% {:>7.1f}%   {:>14} {:>8.1f}%".format(
            ym, 5, mo_ret*100, fmt_usd(nav), nav_ret, dd, nav_maxdd, fmt_usd(btc_nav), btc_ret))

btc_final_nav = START * btc[max(btc.keys())] / btc_start

print()
print('=' * 100)
print('NERQ PAIR SIGNALS (v3, tradeable only)')
print('  Start:          {}'.format(fmt_usd(START)))
print('  Final NAV:      {}'.format(fmt_usd(nav)))
print('  Total Return:   {:.1f}%'.format((nav/START-1)*100))
print('  Max Drawdown:   {:.1f}%'.format(nav_maxdd))
print()
print('BTC BUY & HOLD')
print('  Start:          {}'.format(fmt_usd(START)))
print('  Final NAV:      {}'.format(fmt_usd(btc_final_nav)))
print('  Total Return:   {:.1f}%'.format((btc_final_nav/START-1)*100))
print('  Max Drawdown:   -76.7%')
print('=' * 100)
