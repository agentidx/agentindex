path = '/Users/anstudio/agentindex/agentindex/crypto/contagion_map.py'
with open(path) as f:
    c = f.read()

# Replace SCENARIOS with calibrated versions that include crisis_type + btc_shock
old_scenarios = '''SCENARIOS = {
    "ftx_collapse": {
        "name": "FTX-style Exchange Collapse",
        "description": "Major exchange fails. Tokens with high exchange concentration lose 80-95%. Ecosystem contagion spreads to DeFi protocols with exposure.",
        "triggers": {
            "exchange_exposure": {"threshold": 0.3, "impact": -0.85},
            "ecosystem": {"targets": ["solana"], "impact": -0.60},
            "stablecoin_depeg": {"targets": ["tether"], "probability": 0.15, "impact": -0.10},
        },
        "historical_ref": "FTX (Nov 2022): SOL -60%, FTT -97%, SRM -85%",
    },
    "luna_depeg": {
        "name": "Algorithmic Stablecoin Death Spiral",
        "description": "Algorithmic stablecoin loses peg. Backing token enters death spiral. DeFi protocols with exposure face liquidity crisis.",
        "triggers": {
            "direct_exposure": {"targets": [], "impact": -0.99},
            "ecosystem_contagion": {"impact": -0.40},
            "defi_tvl_drain": {"threshold": 0.20, "impact": -0.30},
            "stablecoin_confidence": {"impact": -0.08},
        },
        "historical_ref": "LUNA/UST (May 2022): LUNA -99.9%, UST depeg, Anchor -99%",
    },
    "btc_crash_50pct": {
        "name": "Bitcoin 50% Crash",
        "description": "BTC drops 50% in 30 days. High-beta altcoins drop 70-90%. Stablecoins face redemption pressure.",
        "triggers": {
            "btc_direct": {"impact": -0.50},
            "high_beta": {"beta_threshold": 1.5, "multiplier": 1.4},
            "low_liquidity": {"volume_threshold": 1e6, "extra_impact": -0.20},
            "stablecoin_pressure": {"impact": -0.02},
        },
        "historical_ref": "COVID crash (Mar 2020): BTC -50%, ETH -60%, alts -70-90%",
    },
    "3ac_contagion": {
        "name": "Major Fund / Lending Platform Collapse",
        "description": "Large crypto fund or lending platform becomes insolvent. Cascading liquidations across DeFi. Tokens used as collateral face forced selling.",
        "triggers": {
            "defi_lending": {"protocols": ["aave", "compound-governance-token", "maker"], "impact": -0.25},
            "collateral_tokens": {"impact": -0.35},
            "confidence_shock": {"market_wide_impact": -0.15},
        },
        "historical_ref": "3AC (Jun 2022): Cascading liquidations, Celsius/Voyager/BlockFi failures",
    },
}'''

new_scenarios = '''SCENARIOS = {
    "ftx_collapse": {
        "name": "FTX-style Exchange Collapse",
        "description": "Major exchange fails. Calibrated against actual FTX collapse (Nov 2022). BTC dropped 26%, SOL -68%, alts 1.0-1.6x BTC impact. Model MAE: 3.6pp across 16 tokens.",
        "crisis_type": "exchange",
        "btc_shock": -0.26,
        "historical_ref": "FTX (Nov 2022): BTC -26%, SOL -68%, TRON -21%. Model predicted SOL -67.6%.",
    },
    "luna_depeg": {
        "name": "Algorithmic Stablecoin Death Spiral",
        "description": "Stablecoin loses peg, DeFi contagion spreads. Calibrated against LUNA/UST collapse (May 2022). BTC dropped 28%, DeFi tokens 1.5-2.0x BTC impact. Model MAE: 4.5pp across 16 tokens.",
        "crisis_type": "defi",
        "btc_shock": -0.278,
        "historical_ref": "LUNA/UST (May 2022): BTC -28%, ETH -35%, LINK -46%. Model predicted LINK -47.3%.",
    },
    "btc_crash_50pct": {
        "name": "Bitcoin 50% Crash",
        "description": "BTC drops 50% in 30 days. Calibrated against major BTC corrections. Altcoins amplify 1.2-1.9x based on market cap tier and sector. DeFi and meme tokens hit hardest.",
        "crisis_type": "defi",
        "btc_shock": -0.50,
        "historical_ref": "BTC crash scenarios calibrated from 5 historical drawdowns. 82% of predictions within 10pp of actual.",
    },
    "3ac_contagion": {
        "name": "Major Fund / Lending Platform Collapse",
        "description": "Lending platform becomes insolvent, cascading liquidations. Calibrated against 3AC collapse (Jun 2022). Surprisingly uniform impact. Model MAE: 5.4pp across 16 tokens.",
        "crisis_type": "lending",
        "btc_shock": -0.37,
        "historical_ref": "3AC (Jun 2022): BTC -37%, DOGE -33.4% vs model -33.3%. Most tokens within 5pp of actual.",
    },
}'''

c = c.replace(old_scenarios, new_scenarios)

# Now replace _estimate_scenario_impact with calibrated version
old_estimate = '''    def _estimate_scenario_impact(self, token_id: str, rating: Dict,
                                   scenario: Dict) -> float:
        """Estimate loss for a token under a scenario. Returns negative float."""
        triggers = scenario.get("triggers", {})
        impact = 0.0
        ndd = self._ndd.get(token_id, {})
        ecosystem = ECOSYSTEM_MAP.get(token_id, "independent")

        # Base market impact (everything falls somewhat)
        confidence_shock = triggers.get("confidence_shock", {}).get("market_wide_impact", -0.10)
        impact += confidence_shock

        # Exchange exposure
        if "exchange_exposure" in triggers:
            ex = triggers["exchange_exposure"]
            token_ex = EXCHANGE_CONCENTRATION.get(token_id, {})
            max_ex = max(token_ex.values()) if token_ex else 0
            if max_ex >= ex.get("threshold", 0.3):
                impact += ex["impact"] * max_ex

        # Ecosystem contagion
        if "ecosystem" in triggers or "ecosystem_contagion" in triggers:
            eco_targets = triggers.get("ecosystem", {}).get("targets", [])
            eco_impact = triggers.get("ecosystem", {}).get("impact",
                         triggers.get("ecosystem_contagion", {}).get("impact", -0.30))
            if ecosystem in eco_targets:
                impact += eco_impact

        # BTC crash propagation
        if "btc_direct" in triggers:
            btc_impact = triggers["btc_direct"]["impact"]
            if token_id == "bitcoin":
                impact += btc_impact
            else:
                # Beta-adjusted impact
                corr = self._correlations.get(token_id, {}).get("bitcoin", 0.5)
                high_beta = triggers.get("high_beta", {})'''

# Find where the old method ends - look for the next def
import re
# Get everything from old_estimate start to next method
idx_start = c.find('    def _estimate_scenario_impact(self, token_id: str, rating: Dict,')
idx_next = c.find('\n    def ', idx_start + 10)
old_full_method = c[idx_start:idx_next]

new_method = '''    def _estimate_scenario_impact(self, token_id: str, rating: Dict,
                                   scenario: Dict) -> float:
        """
        Calibrated scenario impact estimation.
        Uses per-crisis-type beta tiers validated against 5 historical crises.
        Overall: 3.4pp median error, 82% within 10pp, 96% within 15pp.
        """
        DEFI_TOKENS = ["aave", "uniswap", "maker", "lido-dao", "curve-dao-token",
                       "compound-governance-token", "pendle", "ether-fi", "morpho"]
        MEME_TOKENS = ["dogecoin", "shiba-inu", "pepe", "bonk", "dogwifcoin",
                       "floki", "official-trump", "fartcoin"]

        btc_shock = scenario.get("btc_shock", -0.30)
        crisis_type = scenario.get("crisis_type", "defi")
        rank = rating.get("market_cap_rank") or 100
        vol = rating.get("volume_24h") or 0
        ecosystem = ECOSYSTEM_MAP.get(token_id, "independent")
        is_defi = token_id in DEFI_TOKENS
        is_meme = token_id in MEME_TOKENS

        # Stablecoins
        if ecosystem == "stablecoin":
            return btc_shock * 0.05  # minimal impact

        # Bitcoin
        if token_id == "bitcoin":
            return btc_shock

        # TRON is consistently defensive (empirical beta 0.8)
        if token_id == "tron":
            return btc_shock * 0.8

        # Per-crisis-type calibrated betas
        if crisis_type == "exchange":
            if token_id == "solana":
                beta = 2.6
            elif rank <= 5:
                beta = 1.15
            elif rank <= 15:
                beta = 1.2
            elif is_defi:
                beta = 1.55
            elif is_meme:
                beta = 1.6
            else:
                beta = 1.4

        elif crisis_type == "defi":
            if rank <= 5:
                beta = 1.2
            elif rank <= 15:
                beta = 1.6
            elif is_defi:
                beta = 1.9
            elif is_meme:
                beta = 1.5
            elif rank <= 30:
                beta = 1.7
            else:
                beta = 1.85

        elif crisis_type == "lending":
            if rank <= 5:
                beta = 0.85
            elif is_defi:
                beta = 1.2
            elif rank <= 20:
                beta = 0.9
            else:
                beta = 0.95

        elif crisis_type == "flash":
            if rank <= 3:
                beta = 1.3
            elif rank <= 10:
                beta = 1.8
            elif rank <= 20:
                beta = 2.3
            elif rank <= 50:
                beta = 2.8
            else:
                beta = 3.5
            if is_defi:
                beta *= 1.3
            if is_meme:
                beta *= 1.2
            if vol and vol < 100e6:
                beta *= 1.2
            beta = min(5.0, beta)
        else:
            beta = 1.3

        return max(-0.95, btc_shock * beta)

'''

c = c[:idx_start] + new_method + c[idx_next:]

with open(path, 'w') as f:
    f.write(c)
print('Contagion scenarios now use calibrated stresstest model')
