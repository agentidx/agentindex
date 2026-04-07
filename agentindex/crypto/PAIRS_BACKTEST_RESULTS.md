# NERQ Pairs Portfolio Backtest Results (v2)
## Run: 2026-02-26 17:10

### Status: DID NOT PASS ALL CRITERIA

### v2 Filters Applied
- Winsorized returns at +/-200% per leg
- 29 stablecoins excluded
- Min avg daily volume >= $50,000
- NDD filter: no shorting tokens with NDD < 1.5
- Price coverage >= 70%

### Optimized Pillar Weights
| Pillar | Weight |
|--------|--------|
| Ecosystem Strength | 10% |
| Contagion Risk | 30% |
| Historical Resilience | 30% |
| Fundamental Quality | 15% |
| Rug Pull Risk | 15% |

### Results
| Metric | In-Sample | Out-of-Sample | Target |
|--------|-----------|---------------|--------|
| Pairs | 6354 | 9148 | - |
| Hit Rate | 57.5% | 59.0% | >58% |
| Avg Alpha | 2.92% | 4.42% | >0% |
| Median Alpha | 6.67% | 8.45% | - |
| Sharpe | 0.09 | 0.14 | >0.94 (BTC) |
| Max Drawdown | 23826.19% | 32632.20% | - |

### OOS Class Breakdown
| Class | Pairs | Hit Rate | Avg Alpha | Median Alpha |
|-------|-------|----------|-----------|--------------|
| HY_HIGH | 4 | 50.0% | -6.24% | -4.16% |
| IG_HIGH | 91 | 42.9% | -16.34% | -9.61% |
| IG_LOW | 3893 | 52.5% | -3.22% | 1.98% |
| IG_MID | 5160 | 64.2% | 10.55% | 14.45% |

### Methodology
- Long/short pairs within same rating class (quartile selection)
- Hold: 90d, monthly rebalance
- IS: 2021-01-01 to 2023-12-31, OOS: 2024-01-01 to 2025-12-31
