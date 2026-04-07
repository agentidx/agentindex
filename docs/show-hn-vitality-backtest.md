# Show HN Draft — Vitality Backtest Angle

**Title:** Show HN: We backtested a crypto ecosystem score — top quintile lost 44% less in the crash (p<0.001)

**URL:** https://zarq.ai/vitality/backtest

**HN Comment (post immediately after submission):**

Hi HN — we built ZARQ, an independent risk intelligence API for crypto. We rate 15,000+ tokens on a Moody's-style scale with crash probability and distance-to-default.

Our latest addition is the Vitality Score — an ecosystem health metric with 5 weighted dimensions (stress resilience, capital commitment, ecosystem gravity, coordination efficiency, organic momentum).

We backtested it rigorously:
- 3 time windows (Jan 2024, Jan 2025, Jul 2025)
- 355–412 tokens per window
- Out-of-sample methodology, no look-ahead bias
- Winsorized returns, median-based spreads

The crash window (Jul 2025 → Feb 2026) showed a statistically significant result: top-quintile tokens lost 26%, bottom lost 70%. Perfectly monotonic across all 5 quintiles.

Being upfront about limitations:
- Only the crash window is statistically significant (p=0.0008). The other two aren't.
- The model predicts downside protection, not upside.
- Survivorship bias: dead tokens are excluded.
- Crypto returns are fat-tailed — standard p-values should be interpreted cautiously.
- n=412 is large for crypto research but small in absolute terms.

The most predictive dimension is Stress Resilience (+52-66% Q1-Q5 spread). Interestingly, Ecosystem Gravity and Coordination Efficiency show negative spreads — they measure quality but don't predict returns.

Free API, no auth:
- `GET /v1/check/{token}` — trust score, crash probability, vitality score
- `GET /v1/vitality/{token}` — full dimension breakdown
- Bulk data available as JSONL under CC BY 4.0

We're also building the sister platform Nerq (nerq.ai) — an AI agent search engine indexing 5M+ AI assets with trust scores.

Tech stack: FastAPI, SQLite, FAISS + sentence-transformers for semantic search. Running on a Mac Mini behind Cloudflare Tunnel.

Happy to discuss the methodology. Criticism welcome — we'd rather know if there are flaws we haven't caught.
