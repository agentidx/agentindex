# ZARQ CRITICAL EVIDENCE — DO NOT DELETE

These files contain the verified backtest results and analysis code
that prove ZARQ's core claims. Every number on zarq.ai/crypto/alerts
traces back to the code and output in this directory.

## Key Results (OOS: Jan 2024 — Feb 2026, 207 tokens)

| Metric | Value |
|---|---|
| Deaths detected (>80% DD) | 113/113 (100% recall) |
| Precision at >50% crash | 98% (172/176) |
| Precision at >30% crash | 99.4% (175/176) |
| Genuine false positives (<30% DD) | 1/176 (stasis-eurs) |
| Idiosyncratic deaths | 87% (98/113) |
| Idiosyncratic deaths warned | 100% (98/98) |
| Median warning drawdown | -31% |
| Median additional loss avoided | 58% |
| Tokens not warned that stayed healthy | 29/31 (94%) |

## Files

- KEY_QUESTIONS_ANALYSIS.py — Q1/Q2/Q3 analysis (deaths, timing, idiosyncratic)
- FALSE_POSITIVE_ANALYSIS.py — Confusion matrix, precision at all thresholds
- NERQ_BREAKTHROUGH_ANALYSIS.md — Strategic model analysis
- CRASH_MODEL_V3_HANDOVER.md — V3 handover documentation
- crash_prediction_model_v3.py — V3 model code

## How to reproduce

    cd ~/agentindex/agentindex/crypto
    python3 CRITICAL_EVIDENCE/KEY_QUESTIONS_ANALYSIS.py
    python3 CRITICAL_EVIDENCE/FALSE_POSITIVE_ANALYSIS.py

Last verified: 2026-03-01
