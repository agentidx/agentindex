# Reddit r/cryptocurrency Post

**Title:** We backtested a crypto ecosystem health score across the 2025-2026 crash — top-quintile tokens lost 26%, bottom lost 70% (p < 0.001)

**Body:**

We built the Vitality Score at ZARQ — it measures crypto ecosystem health across 5 dimensions (ecosystem gravity, capital commitment, coordination efficiency, stress resilience, organic momentum). Scores 0–100 for 15,000+ tokens.

Then we backtested it honestly across 3 time windows:

**Window C (July 2025 → Feb 2026, the crash):**

| Quintile | Vitality Score | Median Return |
|----------|---------------|---------------|
| Q1 (TOP) | 52.5–67.7 | **-26.1%** |
| Q2 | 43.6–52.3 | -48.8% |
| Q3 | 38.3–43.5 | -55.4% |
| Q4 | 33.3–38.2 | -56.1% |
| Q5 (BOTTOM) | 26.7–33.3 | **-70.4%** |

**Q1–Q5 spread: +44.3%. Perfectly monotonic. t=3.35, p=0.0008.**

Being honest about what it does and doesn't do:
- Only the crash window is statistically significant
- The model predicts **downside protection** better than upside
- Survivorship bias: dead tokens excluded
- Crypto returns are fat-tailed — p-values should be interpreted cautiously

The strongest predictive dimension is **Stress Resilience** (+52-66% Q1-Q5 spread across windows). Ecosystem Gravity and Coordination Efficiency actually show *negative* spreads — they measure quality but don't predict returns.

**How to use it:**
```
GET https://zarq.ai/v1/check/bitcoin
→ trust_score, crash_probability, vitality_score, rating
```

Free API, no auth. 15,000+ tokens rated.

Full backtest results: zarq.ai/vitality/backtest
Rankings: zarq.ai/vitality
Methodology: zarq.ai/vitality/methodology

Not financial advice. Past performance ≠ future results.
