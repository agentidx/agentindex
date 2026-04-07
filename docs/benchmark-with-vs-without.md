# Nerq Benchmark: With vs Without Nerq

**Date:** 2026-03-10T14:56:37Z
**N:** 100 iterations per scenario
**Pool:** 50 agents (15 high-trust + 15 medium-trust + 10 low-trust + 10 dead/not-found)
**Selection:** 5 tools per iteration

## Methodology

- **Without Nerq (baseline):** Randomly select 5 tools from the pool. Call `/v1/agent/kya/{name}` for each. Tools with trust < 40 or not found count as failures.
- **With Nerq:** Call `/v1/preflight?target={name}` for all 50 candidates. Filter to `recommendation == "PROCEED"`. Sort by trust score descending. Pick top 5.
- **Statistical test:** Welch's two-sample t-test (unequal variances). Significance threshold: p < 0.05.

## Tool Pool

| Tier | Count | Description |
|------|-------|-------------|
| High trust (>70) | 15 | Real agents from Nerq index with trust > 70 |
| Medium trust (40-69) | 15 | Real agents from Nerq index with trust 40-69 |
| Low trust (<40) | 10 | Real agents from Nerq index with trust < 40 |
| Dead / not found | 10 | Names that don't exist in the Nerq index |

## Results (N=100 iterations)

| Metric | Without Nerq | With Nerq | Delta |
|--------|-------------|-----------|-------|
| Failure rate (mean +/- SD) | 35.6 +/- 19.8% | 0.0 +/- 0.0% | -35.6% |
| Failure rate 95% CI | [31.7, 39.5]% | [0.0, 0.0]% | |
| Trust score (mean +/- SD) | 68.6 +/- 9.5 | 92.2 +/- 0.0 | +23.6 |
| Trust score 95% CI | [66.8, 70.5] | [92.2, 92.2] | |
| Avg API time | 0.221s | 0.363s | +0.142s |
| Wasted calls | 1.8 | 45.0 | +43.2 |

## Statistical Significance

| Test | Failure Rate | Trust Score |
|------|-------------|-------------|
| t-statistic | 17.9678 | -24.7497 |
| p-value | 0.00000000 | 0.00000000 |
| Significant (p<0.05) | Yes | Yes |

The failure rate difference is **statistically significant** (t=17.968, p=0.00000000).
The trust score difference is **statistically significant** (t=-24.750, p=0.00000000).

## Conclusion

With 100 iterations, Nerq preflight screening produces a statistically significant improvement in both failure rate and trust quality.

For autonomous agents operating without human oversight, Nerq preflight checks provide a quantitative trust gate that prevents interaction with untrusted or dead tools. The screening overhead (0.363s for 50 candidates) is negligible compared to the cost of executing an untrusted tool in production.

---

Data generated from live Nerq API. Reproduce: `python -m agentindex.nerq_benchmark_test`
