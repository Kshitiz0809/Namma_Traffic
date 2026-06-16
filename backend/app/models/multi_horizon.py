"""
Phase 3.5/4 Task 4 — multi-horizon hotspot prediction.

Trains the same CatBoost baseline (reusing the Phase 3 pipeline unchanged —
per instruction) on each of `target_hotspot_15m/30m/60m/90m`, on the same
time-based split, to compare how prediction difficulty changes with horizon
length and recommend an operational horizon.
"""

from __future__ import annotations

import pandas as pd

from app.models.classifier import build_classification_dataset, evaluate_classifier, train_catboost
from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES

HORIZONS_MINUTES = [15, 30, 60, 90]


def run_multi_horizon_comparison(features_df: pd.DataFrame, targets_df: pd.DataFrame) -> pd.DataFrame:
    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    rows = []

    for minutes in HORIZONS_MINUTES:
        target_col = f"target_hotspot_{minutes}m"
        split = build_classification_dataset(features_df, targets_df, target_col)

        X_train = split.train[feature_cols]
        y_train = split.train[target_col].to_numpy()
        X_val = split.val[feature_cols]
        y_val = split.val[target_col].to_numpy()

        model = train_catboost(X_train, y_train, CATEGORICAL_FEATURES)
        proba = model.predict_proba(X_val)[:, 1]
        metrics = evaluate_classifier(f"horizon_{minutes}m", y_val, proba)

        row = metrics.to_dict()
        row["horizon_minutes"] = minutes
        # IMPORTANT: positive_rate rises with horizon length (a 90-minute window
        # is more likely to contain >=1 violation than a 15-minute one just by
        # being longer), which inflates raw PR-AUC — a model that always predicts
        # "positive" would also score better PR-AUC at a higher base rate. "lift"
        # divides PR-AUC by positive_rate as a crude base-rate-normalized signal
        # (a random/always-positive classifier scores lift ~= 1.0; higher is
        # genuinely better, not just a base-rate artifact). See the caveat in
        # docs/horizon_comparison.md before reading raw PR-AUC across horizons.
        row["lift_over_base_rate"] = row["pr_auc"] / row["positive_rate"]
        rows.append(row)

    return pd.DataFrame(rows)


def recommend_horizon(comparison_df: pd.DataFrame) -> dict:
    """Raw PR-AUC is NOT a fair comparison across horizons here (see the
    lift_over_base_rate caveat in run_multi_horizon_comparison) — it rises
    with horizon length partly because longer windows have a higher base
    rate, not purely because longer-horizon predictions are "better."
    `lift_over_base_rate` corrects for this; we recommend the horizon with
    the best lift, breaking ties toward shorter (more actionable) horizons.
    """
    best_row = comparison_df.loc[comparison_df["lift_over_base_rate"].idxmax()]

    return {
        "recommended_horizon_minutes": int(best_row["horizon_minutes"]),
        "pr_auc": float(best_row["pr_auc"]),
        "lift_over_base_rate": float(best_row["lift_over_base_rate"]),
        "rationale": (
            f"Highest base-rate-normalized lift ({best_row['lift_over_base_rate']:.3f}) — "
            f"raw PR-AUC favors longer horizons mainly because they have a higher "
            f"positive rate (60-90m windows are more likely to contain a violation "
            f"just by being longer), which is a base-rate artifact, not a genuine "
            f"improvement in predictive skill. Lift corrects for that."
        ),
    }
