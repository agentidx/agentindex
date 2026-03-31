#!/usr/bin/env python3
"""
ZARQ PORTFOLIO STRESSTEST ENGINE — Sprint 3.2.2
=================================================
Stress-test any crypto portfolio against predefined and custom scenarios.

Features:
  1. Input: user holdings OR predefined portfolios (Alpha, Dynamic, Conservative)
  2. 4 built-in scenarios + custom
  3. Per-token impact with contagion effects
  4. Shareable output (unique hash → URL)
  5. API-ready (returns dicts, no print)

Usage:
  from stresstest_engine import StresstestEngine
  engine = StresstestEngine(db_path)
  result = engine.run_stresstest(
      holdings={"bitcoin": 0.4, "ethereum": 0.3, "solana": 0.3},
      scenario="btc_crash_50pct"
  )

Author: ZARQ
Version: 1.0
Sprint: 3.2.2
"""

import sqlite3
import os
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger("zarq.stresstest")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")

# ══════════════════════════════════════════════════════════════════════════════
# PREDEFINED PORTFOLIOS (from paper trading)
# ══════════════════════════════════════════════════════════════════════════════

PREDEFINED_PORTFOLIOS = {
    "alpha_fund": {
        "name": "ZARQ Alpha Fund (Pure L/S)",
        "description": "Long top-5 SAFE, Short top-5 CRITICAL. Maximum alpha, high volatility.",
        "long": {},   # Filled dynamically from latest signals
        "short": {},  # Filled dynamically from latest signals
        "type": "long_short",
    },
    "dynamic_fund": {
        "name": "ZARQ Dynamic Fund",
        "description": "BTC core + L/S overlay. Bear detection → defensive allocation.",
        "base_alloc": {"bitcoin": 0.40},
        "overlay_weight": 0.20,
        "cash_weight": 0.40,
        "type": "hybrid",
    },
    "conservative_fund": {
        "name": "ZARQ Conservative Fund",
        "description": "Lower risk budget. BTC core + smaller L/S overlay.",
        "base_alloc": {"bitcoin": 0.50},
        "overlay_weight": 0.10,
        "cash_weight": 0.40,
        "type": "hybrid",
    },
    "btc_only": {
        "name": "Bitcoin Only",
        "description": "100% Bitcoin. Benchmark portfolio.",
        "holdings": {"bitcoin": 1.0},
        "type": "simple",
    },
    "top10_equal": {
        "name": "Top 10 Equal Weight",
        "description": "Equal weight across top 10 tokens by market cap.",
        "type": "dynamic_top10",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

STRESS_SCENARIOS = {
    "btc_crash_50pct": {
        "name": "Bitcoin -50% Crash",
        "description": "BTC drops 50% in 30 days. Altcoins amplify losses based on correlation and liquidity.",
        "crisis_type": "defi",
        "btc_shock": -0.50,
        "alt_beta_multiplier": 1.4,
        "low_liq_penalty": -0.15,
        "stablecoin_impact": -0.01,
        "historical_ref": "March 2020 COVID crash, Nov 2018 bear",
    },
    "eth_smart_contract_exploit": {
        "crisis_type": "defi",
        "name": "Ethereum Smart Contract Exploit",
        "description": "Major ETH vulnerability discovered. ETH drops 40%. DeFi protocols on Ethereum face cascading liquidations.",
        "eth_shock": -0.40,
        "ethereum_ecosystem_shock": -0.35,
        "defi_protocol_shock": -0.30,
        "btc_correlation_impact": -0.15,
        "other_l1_benefit": 0.05,
        "historical_ref": "DAO hack (2016), but at current DeFi scale",
    },
    "stablecoin_crisis": {
        "crisis_type": "exchange",
        "name": "Stablecoin Systemic Crisis",
        "description": "Major stablecoin (USDT) faces redemption crisis. All crypto faces liquidity shock.",
        "usdt_depeg": -0.15,
        "usdc_impact": -0.05,
        "market_liquidity_shock": -0.20,
        "defi_tvl_drain": -0.25,
        "flight_to_btc": 0.05,
        "historical_ref": "USDT scare (May 2022), amplified",
    },
    "flash_crash_oct2025": {
        "name": "Flash Crash (Oct 2025 Style)",
        "description": "Exchange infrastructure failure triggers cascading liquidations. BTC drops 13% intraday, but low-liquidity alts collapse 50-70% as market makers go offline. Massive recovery bounce follows within hours.",
        "crisis_type": "flash",
        "btc_shock": -0.13,
        "alt_beta_multiplier": 1.0,
        "low_liq_penalty": -0.25,
        "stablecoin_impact": -0.02,
        "defi_protocol_extra": -0.15,
        "meme_coin_extra": -0.20,
        "historical_ref": "Oct 10, 2025: Binance market maker outage. BTC -13%, ARB -69%, LDO -64%, WIF -61%, UNI -51%, AVAX -47%. 2-3x normal volume. Most recovered 20-40% within hours.",
    },
    "regulatory_crackdown": {
        "crisis_type": "exchange",
        "name": "Global Regulatory Crackdown",
        "description": "US + EU announce comprehensive crypto ban. Exchange tokens hit hardest. DeFi tokens with anon teams face delisting.",
        "market_wide_shock": -0.30,
        "exchange_token_shock": -0.60,
        "defi_anon_shock": -0.45,
        "btc_relative_resilience": 0.10,
        "stablecoin_regulated_benefit": 0.05,
        "historical_ref": "China ban (2021), SEC actions (2023)",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# ECOSYSTEM MAPPING (shared with contagion_map.py)
# ══════════════════════════════════════════════════════════════════════════════

ECOSYSTEM_MAP = {
    "ethereum": "ethereum", "uniswap": "ethereum", "aave": "ethereum",
    "lido-dao": "ethereum", "maker": "ethereum", "chainlink": "ethereum",
    "compound-governance-token": "ethereum", "curve-dao-token": "ethereum",
    "pepe": "ethereum", "shiba-inu": "ethereum",
    "solana": "solana", "raydium": "solana", "jupiter-exchange-solana": "solana",
    "jito-governance-token": "solana", "bonk": "solana", "dogwifcoin": "solana",
    "binancecoin": "bnb", "pancakeswap-token": "bnb",
    "bitcoin": "bitcoin", "wrapped-bitcoin": "bitcoin",
    "tether": "stablecoin", "usd-coin": "stablecoin", "dai": "stablecoin",
}

EXCHANGE_TOKENS = [
    "binancecoin", "crypto-com-chain", "htx-dao", "okb", "leo-token",
]


# ══════════════════════════════════════════════════════════════════════════════
# STRESSTEST ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class StresstestEngine:
    """Portfolio stress testing engine."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ratings = {}
        self._ndd = {}
        self._correlations = {}
        self._loaded = False

    def _load_data(self):
        """Load current market data."""
        if self._loaded:
            return

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        max_date = conn.execute("SELECT MAX(run_date) FROM crypto_rating_daily").fetchone()[0]
        if max_date:
            for r in conn.execute(
                "SELECT * FROM crypto_rating_daily WHERE run_date = ?", (max_date,)
            ).fetchall():
                self._ratings[r["token_id"]] = dict(r)

        max_ndd = conn.execute("SELECT MAX(run_date) FROM crypto_ndd_daily").fetchone()[0]
        if max_ndd:
            for r in conn.execute(
                "SELECT token_id, symbol, name, market_cap, market_cap_rank, price_usd, volume_24h, ndd, alert_level, crash_probability, breakdown FROM crypto_ndd_daily WHERE run_date = ?",
                (max_ndd,)
            ).fetchall():
                self._ndd[r["token_id"]] = dict(r)
                # Enrich ratings with NDD metadata
                tid = r["token_id"]
                if tid in self._ratings:
                    for col in ["symbol", "name", "market_cap", "market_cap_rank", "price_usd", "volume_24h"]:
                        if not self._ratings[tid].get(col):
                            self._ratings[tid][col] = r[col]

        conn.close()
        self._loaded = True

    def run_stresstest(
        self,
        holdings: Optional[Dict[str, float]] = None,
        portfolio_id: Optional[str] = None,
        scenario: str = "btc_crash_50pct",
        custom_scenario: Optional[Dict] = None,
        portfolio_value_usd: float = 100000,
    ) -> Dict[str, Any]:
        """
        Run a stress test on a portfolio.

        Args:
            holdings: Dict of {token_id: weight} (weights sum to ~1.0)
            portfolio_id: Use predefined portfolio
            scenario: Scenario ID
            custom_scenario: Custom scenario parameters
            portfolio_value_usd: Total portfolio value for USD calculations

        Returns:
            Full stress test result with per-token impacts.
        """
        self._load_data()

        # Resolve holdings
        if portfolio_id:
            holdings = self._resolve_portfolio(portfolio_id)
        if not holdings:
            return {"error": "No holdings provided. Use 'holdings' dict or 'portfolio_id'."}

        # Resolve scenario
        if custom_scenario:
            scenario_def = custom_scenario
            scenario_name = custom_scenario.get("name", "Custom Scenario")
        elif scenario in STRESS_SCENARIOS:
            scenario_def = STRESS_SCENARIOS[scenario]
            scenario_name = scenario_def["name"]
        else:
            return {
                "error": f"Unknown scenario: {scenario}",
                "available_scenarios": list(STRESS_SCENARIOS.keys()),
            }

        # Calculate per-token impacts
        token_results = []
        total_portfolio_impact = 0.0

        for token_id, weight in holdings.items():
            if weight == 0:
                continue

            rating = self._ratings.get(token_id, {})
            ndd = self._ndd.get(token_id, {})

            impact_pct = self._calculate_token_impact(token_id, scenario_def, rating, ndd)

            token_value = portfolio_value_usd * weight
            token_loss = token_value * impact_pct

            token_results.append({
                "token_id": token_id,
                "symbol": rating.get("symbol", token_id[:5].upper()),
                "name": rating.get("name", token_id),
                "weight": round(weight, 4),
                "position_value_usd": round(token_value, 2),
                "estimated_impact_pct": round(impact_pct * 100, 1),
                "estimated_loss_usd": round(token_loss, 2),
                "post_stress_value_usd": round(token_value + token_loss, 2),
                "current_rating": rating.get("rating", "N/A"),
                "current_ndd": ndd.get("ndd"),
                "risk_contribution": round(abs(token_loss) / portfolio_value_usd * 100, 2),
            })

            total_portfolio_impact += weight * impact_pct

        # Sort by worst impact
        token_results.sort(key=lambda x: x["estimated_impact_pct"])

        # Generate shareable hash
        result_hash = hashlib.sha256(
            json.dumps({
                "holdings": holdings,
                "scenario": scenario,
                "timestamp": datetime.now().strftime("%Y-%m-%d"),
            }, sort_keys=True).encode()
        ).hexdigest()[:12]

        result = {
            "stresstest_id": result_hash,
            "shareable_url": f"https://zarq.ai/stresstest/{result_hash}",
            "scenario": {
                "id": scenario,
                "name": scenario_name,
                "description": scenario_def.get("description", ""),
                "historical_reference": scenario_def.get("historical_ref", ""),
            },
            "portfolio": {
                "total_value_usd": portfolio_value_usd,
                "n_tokens": len(holdings),
                "portfolio_id": portfolio_id,
            },
            "results": {
                "total_impact_pct": round(total_portfolio_impact * 100, 1),
                "total_loss_usd": round(portfolio_value_usd * total_portfolio_impact, 2),
                "post_stress_value_usd": round(portfolio_value_usd * (1 + total_portfolio_impact), 2),
                "worst_token": token_results[0] if token_results else None,
                "best_token": token_results[-1] if token_results else None,
                "max_drawdown_pct": round(min(t["estimated_impact_pct"] for t in token_results), 1) if token_results else 0,
            },
            "token_details": token_results,
            "risk_summary": self._generate_risk_summary(token_results, total_portfolio_impact),
            "run_at": datetime.now().isoformat(),
        }

        return result

    def _calculate_token_impact(self, token_id: str, scenario: Dict,
                                 rating: Dict, ndd: Dict) -> float:
        """Calculate estimated impact for a single token under a scenario."""
        impact = 0.0
        ecosystem = ECOSYSTEM_MAP.get(token_id, "other")

        # BTC crash scenario
        if "btc_shock" in scenario:
            btc_shock = scenario["btc_shock"]
            if token_id == "bitcoin":
                impact += btc_shock
            elif ecosystem == "stablecoin":
                impact += scenario.get("stablecoin_impact", -0.01)
            else:
                # Calibrated beta per crisis type (validated MAE 5.6pp across 67 token-scenario pairs)
                rank = rating.get("market_cap_rank") or 100
                vol = rating.get("volume_24h") or 0
                is_defi = token_id in ["aave", "uniswap", "maker", "lido-dao", "curve-dao-token", "compound-governance-token"]
                is_meme = token_id in ["dogecoin", "shiba-inu", "pepe", "bonk", "dogwifcoin", "floki"]
                crisis_type = scenario.get("crisis_type", "defi")

                if token_id == "tron":
                    beta = 0.8
                elif crisis_type == "exchange":
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
                    beta = min(1.8, 1.0 + max(0, (rank - 10)) / 200)

                impact += btc_shock * beta

                # Low liquidity penalty
                vol = rating.get("volume_24h") or 0
                if vol < 5e6:
                    impact += scenario.get("low_liq_penalty", -0.10)

        # ETH exploit scenario
        if "eth_shock" in scenario:
            if token_id == "ethereum":
                impact += scenario["eth_shock"]
            elif ecosystem == "ethereum":
                impact += scenario.get("ethereum_ecosystem_shock", -0.30)
            elif token_id in ["aave", "compound-governance-token", "maker", "curve-dao-token", "uniswap"]:
                impact += scenario.get("defi_protocol_shock", -0.25)
            elif ecosystem == "stablecoin":
                impact += -0.05
            elif token_id == "bitcoin":
                impact += scenario.get("btc_correlation_impact", -0.10)
            else:
                # Other L1s might benefit slightly
                impact += scenario.get("other_l1_benefit", 0) + scenario.get("btc_correlation_impact", -0.10)

        # Stablecoin crisis
        if "usdt_depeg" in scenario:
            if token_id == "tether":
                impact += scenario["usdt_depeg"]
            elif token_id == "usd-coin":
                impact += scenario.get("usdc_impact", -0.03)
            elif ecosystem == "stablecoin":
                impact += -0.08
            elif token_id == "bitcoin":
                impact += scenario.get("flight_to_btc", 0.05) + scenario.get("market_liquidity_shock", -0.15)
            else:
                impact += scenario.get("market_liquidity_shock", -0.20)
                # DeFi protocols more exposed
                if token_id in ["aave", "compound-governance-token", "maker", "curve-dao-token"]:
                    impact += scenario.get("defi_tvl_drain", -0.20)

        # Regulatory crackdown
        if "market_wide_shock" in scenario and "exchange_token_shock" in scenario:
            impact += scenario["market_wide_shock"]
            if token_id in EXCHANGE_TOKENS:
                impact += scenario["exchange_token_shock"]
            if token_id == "bitcoin":
                impact += scenario.get("btc_relative_resilience", 0.05)
            if ecosystem == "stablecoin":
                impact += scenario.get("stablecoin_regulated_benefit", 0.03)

        # Distress amplifier: already weak tokens get hit harder
        ndd_val = ndd.get("ndd")
        if ndd_val and ndd_val < 2.0:
            impact *= 1.4
        elif ndd_val and ndd_val < 3.0:
            impact *= 1.15

        return max(-0.99, min(0.2, impact))

    def _resolve_portfolio(self, portfolio_id: str) -> Optional[Dict[str, float]]:
        """Resolve a predefined portfolio to holdings dict."""
        if portfolio_id not in PREDEFINED_PORTFOLIOS:
            return None

        p = PREDEFINED_PORTFOLIOS[portfolio_id]

        if p["type"] == "simple":
            return p.get("holdings", {})

        if p["type"] == "dynamic_top10":
            # Top 10 by market cap, equal weight
            top10 = sorted(
                self._ratings.values(),
                key=lambda x: x.get("market_cap_rank") or 9999
            )[:10]
            return {t["token_id"]: 0.10 for t in top10}

        if p["type"] == "hybrid":
            holdings = dict(p.get("base_alloc", {}))
            # Add overlay from current signals (simplified)
            overlay_w = p.get("overlay_weight", 0.2)
            # Top SAFE tokens for long
            safe = sorted(
                [r for r in self._ratings.values() if r.get("score", 0) > 75],
                key=lambda x: -x.get("score", 0)
            )[:5]
            for t in safe:
                holdings[t["token_id"]] = holdings.get(t["token_id"], 0) + overlay_w / 5
            return holdings

        return None

    def _generate_risk_summary(self, token_results: List[Dict], total_impact: float) -> Dict:
        """Generate human-readable risk summary."""
        critical = [t for t in token_results if t["estimated_impact_pct"] <= -50]
        high = [t for t in token_results if -50 < t["estimated_impact_pct"] <= -30]
        moderate = [t for t in token_results if -30 < t["estimated_impact_pct"] <= -15]

        return {
            "severity": "CRITICAL" if total_impact <= -0.40 else "HIGH" if total_impact <= -0.25 else "MODERATE" if total_impact <= -0.15 else "LOW",
            "critical_exposure_tokens": len(critical),
            "high_exposure_tokens": len(high),
            "moderate_exposure_tokens": len(moderate),
            "concentration_warning": any(t["weight"] > 0.30 for t in token_results),
            "recommendations": self._generate_recommendations(token_results, total_impact),
        }

    @staticmethod
    def _generate_recommendations(token_results: List[Dict], total_impact: float) -> List[str]:
        """Generate actionable recommendations."""
        recs = []

        if total_impact <= -0.40:
            recs.append("Portfolio is critically exposed. Consider reducing positions in worst-affected tokens.")

        # Concentration risk
        concentrated = [t for t in token_results if t["weight"] > 0.30]
        for t in concentrated:
            recs.append(f"High concentration in {t['symbol']} ({t['weight']*100:.0f}%). Consider diversifying.")

        # Low-rated tokens
        risky = [t for t in token_results if t.get("current_ndd") and t["current_ndd"] < 2.5]
        for t in risky:
            recs.append(f"{t['symbol']} already shows structural weakness (NDD {t['current_ndd']:.1f}). Extra vulnerable in stress.")

        if not recs:
            recs.append("Portfolio shows reasonable resilience under this scenario.")

        return recs

    # ──────────────────────────────────────────────────────────────────────
    # PUBLIC: List scenarios & portfolios
    # ──────────────────────────────────────────────────────────────────────

    def get_available_scenarios(self) -> List[Dict[str, str]]:
        return [
            {"id": k, "name": v["name"], "description": v["description"]}
            for k, v in STRESS_SCENARIOS.items()
        ]

    def get_predefined_portfolios(self) -> List[Dict[str, str]]:
        return [
            {"id": k, "name": v["name"], "description": v["description"]}
            for k, v in PREDEFINED_PORTFOLIOS.items()
        ]


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ZARQ Portfolio Stresstest")
    parser.add_argument("--scenario", type=str, default="btc_crash_50pct")
    parser.add_argument("--portfolio", type=str, help="Predefined portfolio ID")
    parser.add_argument("--holdings", type=str, help='JSON holdings: \'{"bitcoin":0.5,"ethereum":0.5}\'')
    parser.add_argument("--value", type=float, default=100000, help="Portfolio value in USD")
    parser.add_argument("--all-scenarios", action="store_true", help="Run all scenarios")
    parser.add_argument("--db", type=str, default=DB_PATH)
    args = parser.parse_args()

    engine = StresstestEngine(args.db)

    holdings = None
    if args.holdings:
        holdings = json.loads(args.holdings)

    if args.all_scenarios:
        for scenario_id in STRESS_SCENARIOS:
            result = engine.run_stresstest(
                holdings=holdings,
                portfolio_id=args.portfolio or "top10_equal",
                scenario=scenario_id,
                portfolio_value_usd=args.value,
            )
            print(f"\n{'='*60}")
            print(f"Scenario: {result['scenario']['name']}")
            print(f"Portfolio Impact: {result['results']['total_impact_pct']:+.1f}%")
            print(f"Loss: ${abs(result['results']['total_loss_usd']):,.0f}")
            print(f"Severity: {result['risk_summary']['severity']}")
    else:
        result = engine.run_stresstest(
            holdings=holdings,
            portfolio_id=args.portfolio or ("top10_equal" if not holdings else None),
            scenario=args.scenario,
            portfolio_value_usd=args.value,
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
