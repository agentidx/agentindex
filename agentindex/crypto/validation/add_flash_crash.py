path = '/Users/anstudio/agentindex/agentindex/crypto/stresstest_engine.py'
with open(path) as f:
    c = f.read()

# Add the Oct 2025 flash crash scenario
old_scenarios_end = """    "regulatory_crackdown": {"""

new_scenario_plus = """    "flash_crash_oct2025": {
        "name": "Flash Crash (Oct 2025 Style)",
        "description": "Exchange infrastructure failure triggers cascading liquidations. BTC drops 13% intraday, but low-liquidity alts collapse 50-70% as market makers go offline. Massive recovery bounce follows within hours.",
        "btc_shock": -0.13,
        "alt_beta_multiplier": 1.0,
        "low_liq_penalty": -0.25,
        "stablecoin_impact": -0.02,
        "defi_protocol_extra": -0.15,
        "meme_coin_extra": -0.20,
        "historical_ref": "Oct 10, 2025: Binance market maker outage. BTC -13%, ARB -69%, LDO -64%, WIF -61%, UNI -51%, AVAX -47%. 2-3x normal volume. Most recovered 20-40% within hours.",
    },
    "regulatory_crackdown": {"""

c = c.replace(old_scenarios_end, new_scenario_plus)

# Add flash crash logic in _calculate_token_impact
old_stablecoin_check = """        # Stablecoin crisis
        if "usdt_depeg" in scenario:"""

flash_logic = """        # Flash crash (Oct 2025 style)
        if "defi_protocol_extra" in scenario and "meme_coin_extra" in scenario:
            btc_shock = scenario.get("btc_shock", -0.13)
            if token_id == "bitcoin":
                impact += btc_shock
            elif ecosystem == "stablecoin":
                impact += scenario.get("stablecoin_impact", -0.02)
            else:
                rank = rating.get("market_cap_rank") or 100
                # Flash crashes hit low-cap tokens exponentially harder
                beta = min(3.5, 1.0 + max(0, (rank - 5)) / 30)
                impact += btc_shock * beta
                # Low liquidity amplifier (massive in flash crashes)
                vol = rating.get("volume_24h") or 0
                if vol < 50e6:
                    impact += scenario.get("low_liq_penalty", -0.25)
                elif vol < 200e6:
                    impact += scenario.get("low_liq_penalty", -0.25) * 0.5
                # DeFi protocols extra exposed
                if token_id in ["aave", "uniswap", "maker", "curve-dao-token", "lido-dao", "compound-governance-token"]:
                    impact += scenario.get("defi_protocol_extra", -0.15)
                # Meme coins get destroyed
                if token_id in ["dogecoin", "shiba-inu", "pepe", "bonk", "dogwifcoin", "floki"]:
                    impact += scenario.get("meme_coin_extra", -0.20)

        # Stablecoin crisis
        if "usdt_depeg" in scenario:"""

c = c.replace(old_stablecoin_check, flash_logic + "\n\n        " + old_stablecoin_check.lstrip())

with open(path, 'w') as f:
    f.write(c)
print("Added flash crash scenario to stresstest engine")

# Now add to the frontend dropdown
path2 = '/Users/anstudio/agentindex/agentindex/crypto/zarq_risk_pages.py'
with open(path2) as f:
    c2 = f.read()

# Add option to select
old_select_opts = """<option value="btc_crash_50pct">Bitcoin -50% Crash</option>
      <option value="eth_smart_contract_exploit">Ethereum Smart Contract Exploit</option>"""

new_select_opts = """<option value="btc_crash_50pct">Bitcoin -50% Crash</option>
      <option value="flash_crash_oct2025">Flash Crash (Oct 2025 Style)</option>
      <option value="eth_smart_contract_exploit">Ethereum Smart Contract Exploit</option>"""

c2 = c2.replace(old_select_opts, new_select_opts)

# Add scenario description
old_desc_btc = """  btc_crash_50pct: {"""
new_desc_with_flash = """  flash_crash_oct2025: {
    title: 'Flash Crash (Oct 2025 Style)',
    desc: 'Exchange infrastructure failure triggers cascading liquidations. BTC drops 13% intraday but low-liquidity altcoins collapse 50-70% as market makers go offline. DeFi protocols lose 50%+ as liquidation bots can\\u2019t execute. Meme coins see 45-60% wicks. Recovery bounce of 20-40% follows within hours, but not all tokens recover fully.',
    why: 'This actually happened Oct 10, 2025 when Binance market makers went offline. ARB dropped 69%, LDO 64%, WIF 61%. It exposed how dependent crypto liquidity is on a few market makers. Tests your portfolio\\u2019s flash crash resilience \\u2014 especially low-cap and DeFi exposure.'
  },
  btc_crash_50pct: {"""

c2 = c2.replace(old_desc_btc, new_desc_with_flash)

# Add to validation evidence section
old_3ac_evidence = """<div style="padding:12px;background:var(--white);border:1px solid var(--gray-200)">
          <div style="font-family:var(--mono);font-size:12px;font-weight:600">3AC Contagion</div>"""

new_flash_plus_3ac = """<div style="padding:12px;background:var(--white);border:1px solid var(--gray-200)">
          <div style="font-family:var(--mono);font-size:12px;font-weight:600">Flash Crash Oct 2025</div>
          <div style="font-family:var(--mono);font-size:10px;color:var(--gray-500)">Oct 10, 2025</div>
          <div style="margin-top:8px;font-family:var(--mono);font-size:11px">ARB: <span style="color:var(--red)">-69%</span> flash &middot; LDO: <span style="color:var(--red)">-64%</span></div>
          <div style="font-family:var(--mono);font-size:11px">BTC: <span style="color:var(--red)">-13%</span> &middot; DOGE: <span style="color:var(--red)">-45%</span></div>
          <div style="font-family:var(--mono);font-size:10px;color:var(--warm);margin-top:4px">Low-cap tokens hit 3-5x harder than BTC</div>
        </div>
        <div style="padding:12px;background:var(--white);border:1px solid var(--gray-200)">
          <div style="font-family:var(--mono);font-size:12px;font-weight:600">3AC Contagion</div>"""

c2 = c2.replace(old_3ac_evidence, new_flash_plus_3ac)

# Change grid to 5 columns for the validation boxes
c2 = c2.replace(
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px">',
    '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px">',
    1  # only the validation grid, not the top metrics
)

with open(path2, 'w') as f:
    f.write(c2)
print("Added flash crash to frontend")
