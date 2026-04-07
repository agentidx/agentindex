# Reddit r/defi Post

**Title:** Free API: Moody's-style ratings + crash probability for 15K tokens, now with DEX velocity scoring

**Body:**

Built ZARQ — an independent risk intelligence API for crypto. Rates 15,000+ tokens on a Moody's-style scale (Aaa to D) with crash probability, distance-to-default, and a new Vitality Score measuring ecosystem health.

**What makes it useful for DeFi:**

1. **Pre-trade safety check** — `GET /v1/crypto/safety/{token}` returns risk verdict in <100ms. Designed for agents and bots that need to gate swaps.

2. **Crash probability** — Our structural collapse model has 100% recall on 113 historical token deaths, 98% precision, 22-month average lead time.

3. **Vitality Score** — measures ecosystem quality across 5 dimensions. Just added DEX velocity (volume/TVL ratio from DeFiLlama) to Capital Commitment. Backtested: high-Vitality tokens lost 44% less in the 2025-2026 crash (p < 0.001).

4. **DeFi yield risk** — zarq.ai/yield-risk shows safe yields vs dangerous APY across thousands of pools.

5. **Portfolio stress test** — `POST /v1/crypto/stresstest` with your holdings, get scenario analysis.

**Quick check:**
```
GET https://zarq.ai/v1/check/ethereum
→ {"verdict": "WARNING", "trust_score": 74.52, "crash_probability": 0.32, "vitality_score": 68.8, ...}
```

Free API, no auth, 5000 req/day. Bulk data available as JSONL (CC BY 4.0).

API docs: zarq.ai/docs
Crash watch: zarq.ai/crash-watch
Yield risk: zarq.ai/yield-risk

Anyone integrating risk checks into their DeFi bots? Curious what signals you care about most.
