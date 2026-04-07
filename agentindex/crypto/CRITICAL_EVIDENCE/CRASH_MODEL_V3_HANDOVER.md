# NERQ SPRINT 2.0 — SESSION HANDOVER: Crash Model v3
**Date:** 2026-02-28 (Nattpass)
**Continues from:** SPRINT2_HANDOVER.md

---

## WHAT WAS BUILT THIS SESSION

### crash_prediction_model_v3.py — Complete Pipeline

Self-contained script that implements all 6 steps from the handover instructions:

**Step 1: TVL-based features (4 new)**
- `tvl_momentum_7d` — TVL % change over 7 days
- `tvl_momentum_30d` — TVL % change over 30 days
- `tvl_drawdown` — Current TVL vs 90-day peak (catches bleeding TVL)
- `tvl_vs_price_divergence` — TVL_change_30d minus price_change_30d (THE key signal: TVL leaving while price holds = danger)

**Step 2: Audit/structural features (4 new)**
- `has_audit` — Binary, from DeFiLlama audit_count
- `is_fork` — Binary, from forked_from field
- `category_risk` — Mapped from protocol category (Algo-Stables=1.0, CEX=0.2, etc.)
- `protocol_age_days` — Days since listed, normalized to years

**Step 3: Stablecoin flow features (1 new)**
- `chain_stablecoin_change_30d` — Stablecoin supply change on the token's chain over 30d. Negative = capital flight.
- Maps tokens → chains via `crypto_token_ecosystem_v2` in reference DB

**Step 4: Yield anomaly features (1 new)**
- `yield_anomaly` — Normalized max APY on the protocol. >100% APY flagged as unsustainable risk.

**Step 5: Combined model training**
- Reconstructs ALL v2 features from DB (no dependency on crash_model_v2.json — it's loaded for reference but not required)
- 19 v2 features + 13 new v3 features = 32 total features
- New v3 interaction features:
  - `ix_tvl_div_x_trust` — TVL divergence × inverse trust maintenance (catches "looks healthy but TVL bleeding")
  - `ix_no_audit_x_drawdown` — No audit × drawdown severity (unaudited + falling = danger)
- `has_tvl_data` flag — Allows model to learn different weights for tokens with/without TVL data
- Logistic regression trained from scratch (no sklearn dependency)
- IS/OOS split: 2021-2023 IS, 2024-2026 OOS
- L2 regularization to prevent overfitting
- Trains BOTH v2 (19 features) and v3 (32 features) for head-to-head comparison

**Step 6: Severity analysis**
- Replicates severe_crash_analysis.py logic on both v2 and v3
- Tests all severity levels: mild, severe, catastrophic, terminal, never-recover
- Tests at 30%, 40%, 50% thresholds
- Wilson score confidence intervals
- **TVL vs non-TVL subgroup analysis** — Do tokens WITH TVL data get better predictions?

---

## OUTPUT

When run on the server, the script produces:
1. **Console output** — Full training log with AUC comparisons, severity tables, feature importance
2. **crash_model_v3.json** — Saved model weights, bias, feature means/stds
3. **crash_model_v3_predictions** — DB table with v2 and v3 predictions side by side

---

## HOW TO RUN (Dagpass)

```bash
# 1. Copy to server
cp ~/Downloads/crash_prediction_model_v3.py ~/agentindex/agentindex/crypto/

# 2. Run it
cd ~/agentindex/agentindex/crypto && python3 crash_prediction_model_v3.py

# 3. If it fails, check these common issues:
#    - Table names might differ: run sqlite3 crypto_trust.db ".tables" to verify
#    - Column names in crypto_ndd_daily might differ from what's assumed
#    - The reference DB path might need adjustment
```

---

## KEY DESIGN DECISIONS

1. **No sklearn dependency** — Logistic regression implemented from scratch. The server may not have sklearn installed and we want zero dependency issues.

2. **Graceful degradation for missing TVL** — Only 79/207 tokens have TVL data. The `has_tvl_data` flag lets the model learn separate behavior. Tokens without TVL get zeroed TVL features, which the model can compensate for.

3. **V2 features reconstructed from DB** — Rather than depending on crash_model_v2.json being perfect, the script rebuilds v2 features from raw DB tables. This ensures consistency and makes the script self-contained.

4. **Head-to-head comparison** — Trains both v2 (19 features) and v3 (32 features) on the SAME data split, so the AUC improvement is directly comparable.

5. **Category risk mapping** — Hand-coded based on DeFi risk knowledge. Algo-Stables highest risk (1.0), CEX lowest (0.2). This is a strong prior that should help catch structurally risky protocols.

---

## WHAT TO LOOK FOR IN THE OUTPUT

### Primary metric: Never-recover detection at >40% threshold
- **V2 baseline:** 63% OOS
- **Target:** 80%+
- **If improved:** The TVL divergence signal is working. "We saw the TVL bleeding before the price crashed."
- **If NOT improved:** The 79/207 token coverage might be too sparse. Consider: are the never-recover tokens in the TVL-matched set or not?

### Secondary: AUC
- **V2 baseline:** 0.708 OOS
- **Any improvement here is bonus.** The real value is in the severity tail, not overall AUC.

### Feature importance
- If `tvl_vs_price_divergence` or `ix_tvl_div_x_trust` rank in top 10, the "hidden risk" thesis is validated.
- If `has_audit` or `category_risk` rank high, structural features matter.

### TVL subgroup
- If tokens WITH TVL data have significantly higher detection rates, that proves the data value.
- This is a strong narrative for exit: "With on-chain data, our detection rate goes from X% to Y%."

---

## REMAINING FROM SPRINT 2.0 HANDOVER

All items from the previous handover still apply. This session addressed only the "Next: Build Hidden Risk Features" section. The full Sprint 2.0/2.5 remaining items (API deployment, MCP integration, IS/OOS for HC Alert, etc.) are unchanged.

---

## FILES FOR NEXT SESSION
1. **crash_prediction_model_v3.py** — This session's output, ready to run
2. **SPRINT2_HANDOVER.md** — Previous session context (still valid)
3. **SPRINT_PROGRESS_HANDOVER.md** — Overall sprint progress
4. **NERQ_CRYPTO_SPRINT_PLAN_V3_1_1_DAG_NATT.md** — Master plan
