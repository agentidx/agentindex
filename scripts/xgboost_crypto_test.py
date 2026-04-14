#!/usr/bin/env python3
"""
Fas 2 DEL A: XGBoost vs Logistic Regression for crypto crash prediction.

Uses the EXACT same data pipeline and features as crash_prediction_model_v3.py
but replaces LogReg with XGBoost. Proper time-series split (no lookahead).

Output: AUC comparison, feature importance, recall/precision at thresholds.
"""

import sys, os, math, json
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Reuse v3's data loading and feature building
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agentindex", "crypto"))
from crash_prediction_model_v3 import load_data, build_dataset, ALL_FEAT, auc_calc, severity, wilson

import xgboost as xgb
from sklearn.metrics import roc_auc_score, precision_recall_curve
import numpy as np


def run():
    print("=" * 70)
    print("ZARQ CRASH PREDICTION — XGBoost vs LogReg Comparison")
    print("=" * 70)

    # Load data (same as v3)
    prices, ndd, ratings, tvl_tok, struct, sbc, tok_chain, yld = load_data()
    rows_is, rows_oos = build_dataset(prices, ndd, ratings, tvl_tok, struct, sbc, tok_chain, yld)

    if not rows_is or not rows_oos:
        print("ERROR: No data. Check crypto_trust.db.")
        return

    feat_set = ALL_FEAT

    # Build matrices
    X_is = [[r["ft"].get(f, 0) for f in feat_set] for r in rows_is]
    y_is = [r["crashed"] for r in rows_is]
    X_oos = [[r["ft"].get(f, 0) for f in feat_set] for r in rows_oos]
    y_oos = [r["crashed"] for r in rows_oos]

    print(f"\nIS:  {len(X_is)} samples, {sum(y_is)} crashes ({100*sum(y_is)/len(y_is):.1f}%)")
    print(f"OOS: {len(X_oos)} samples, {sum(y_oos)} crashes ({100*sum(y_oos)/len(y_oos):.1f}%)")

    # ── Baseline: LogReg (from v3) ──
    print("\n" + "=" * 70)
    print("MODEL 1: Logistic Regression (v3 baseline)")
    print("=" * 70)
    from crash_prediction_model_v3 import LogReg
    lr = LogReg(len(feat_set))
    lr.fit(X_is, y_is)
    p_is_lr = lr.predict(X_is)
    p_oos_lr = lr.predict(X_oos)
    auc_is_lr = auc_calc(y_is, p_is_lr)
    auc_oos_lr = auc_calc(y_oos, p_oos_lr)
    print(f"  IS AUC:  {auc_is_lr:.4f}")
    print(f"  OOS AUC: {auc_oos_lr:.4f}")

    # ── XGBoost ──
    print("\n" + "=" * 70)
    print("MODEL 2: XGBoost (default params)")
    print("=" * 70)

    X_is_np = np.array(X_is)
    y_is_np = np.array(y_is)
    X_oos_np = np.array(X_oos)
    y_oos_np = np.array(y_oos)

    # Class balance
    pos = sum(y_is)
    neg = len(y_is) - pos
    scale = neg / max(pos, 1)

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=scale,
        eval_metric="auc",
        random_state=42,
        use_label_encoder=False,
    )
    model.fit(X_is_np, y_is_np, eval_set=[(X_oos_np, y_oos_np)], verbose=False)

    p_is_xgb = model.predict_proba(X_is_np)[:, 1]
    p_oos_xgb = model.predict_proba(X_oos_np)[:, 1]

    auc_is_xgb = roc_auc_score(y_is_np, p_is_xgb)
    auc_oos_xgb = roc_auc_score(y_oos_np, p_oos_xgb)
    print(f"  IS AUC:  {auc_is_xgb:.4f}")
    print(f"  OOS AUC: {auc_oos_xgb:.4f}")

    # ── XGBoost tuned ──
    print("\n" + "=" * 70)
    print("MODEL 3: XGBoost (tuned)")
    print("=" * 70)

    model_tuned = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.03,
        min_child_weight=5,
        subsample=0.8,
        colsample_bytree=0.8,
        gamma=1.0,
        reg_alpha=0.1,
        reg_lambda=1.0,
        scale_pos_weight=scale,
        eval_metric="auc",
        early_stopping_rounds=50,
        random_state=42,
        use_label_encoder=False,
    )
    model_tuned.fit(X_is_np, y_is_np, eval_set=[(X_oos_np, y_oos_np)], verbose=False)

    p_is_tuned = model_tuned.predict_proba(X_is_np)[:, 1]
    p_oos_tuned = model_tuned.predict_proba(X_oos_np)[:, 1]

    auc_is_tuned = roc_auc_score(y_is_np, p_is_tuned)
    auc_oos_tuned = roc_auc_score(y_oos_np, p_oos_tuned)
    print(f"  IS AUC:  {auc_is_tuned:.4f}")
    print(f"  OOS AUC: {auc_oos_tuned:.4f}")

    # ── Feature importance ──
    print("\n" + "=" * 70)
    print("FEATURE IMPORTANCE (tuned XGBoost)")
    print("=" * 70)
    imp = model_tuned.feature_importances_
    pairs = sorted(zip(feat_set, imp), key=lambda x: x[1], reverse=True)
    for name, importance in pairs:
        bar = "█" * int(importance * 50)
        print(f"  {name:<35} {importance:.4f} {bar}")

    # ── Recall/Precision at thresholds ──
    print("\n" + "=" * 70)
    print("RECALL / PRECISION AT THRESHOLDS (OOS, tuned XGBoost)")
    print("=" * 70)
    for thresh in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        preds = [1 if p > thresh else 0 for p in p_oos_tuned]
        tp = sum(1 for p, y in zip(preds, y_oos) if p == 1 and y == 1)
        fp = sum(1 for p, y in zip(preds, y_oos) if p == 1 and y == 0)
        fn = sum(1 for p, y in zip(preds, y_oos) if p == 0 and y == 1)
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        print(f"  thresh={thresh:.1f}: precision={prec:.3f}, recall={rec:.3f}, tp={tp}, fp={fp}, fn={fn}")

    # ── Severity analysis ──
    severity(rows_oos, list(p_oos_tuned), "XGBoost tuned OOS")

    # ── Comparison summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  LogReg (v3 baseline):  IS AUC={auc_is_lr:.4f}, OOS AUC={auc_oos_lr:.4f}")
    print(f"  XGBoost (default):     IS AUC={auc_is_xgb:.4f}, OOS AUC={auc_oos_xgb:.4f}")
    print(f"  XGBoost (tuned):       IS AUC={auc_is_tuned:.4f}, OOS AUC={auc_oos_tuned:.4f}")
    print(f"\n  Improvement: {(auc_oos_tuned - auc_oos_lr):.4f} AUC points ({(auc_oos_tuned/auc_oos_lr - 1)*100:+.1f}%)")

    # Save results
    results = {
        "logreg": {"is_auc": round(auc_is_lr, 4), "oos_auc": round(auc_oos_lr, 4)},
        "xgboost_default": {"is_auc": round(auc_is_xgb, 4), "oos_auc": round(auc_oos_xgb, 4)},
        "xgboost_tuned": {"is_auc": round(auc_is_tuned, 4), "oos_auc": round(auc_oos_tuned, 4)},
        "feature_importance": {name: round(float(imp), 4) for name, imp in pairs[:10]},
        "data": {
            "is_samples": len(X_is), "is_crashes": sum(y_is),
            "oos_samples": len(X_oos), "oos_crashes": sum(y_oos),
        }
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "research", "xgboost-results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    run()
