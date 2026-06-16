"""
Final robustness experiment before feature lock — Reduced-Spatial-Identity
Model (DECISIONS.md ADR-019). Measures how much predictive power remains
without direct spatial-grid identity (h3_cell/geohash), given the spatial
holdout FAIL and SHAP h3_cell-dominance finding from Phase 3.5.

Model A = the existing Phase 3 winning model (loaded, NOT retrained).
Model B = ONE new training run with h3_cell/geohash removed from the
categorical feature set, everything else unchanged. Per instruction: no
architecture changes, no additional variants beyond this single comparison.
"""

from __future__ import annotations

import pandas as pd
from catboost import CatBoostClassifier

from app.models.classifier import build_classification_dataset, evaluate_classifier, train_catboost
from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES, REDUCED_SPATIAL_CATEGORICAL_FEATURES

PR_AUC_DROP_PASS_THRESHOLD_PCT = 3.0


def run_spatial_dependency_experiment(
    features_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    model_a_path: str,
    target_col: str = "target_hotspot_60m",
) -> dict:
    full_feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    reduced_feature_cols = NUMERIC_FEATURES + REDUCED_SPATIAL_CATEGORICAL_FEATURES

    # Model A: load the existing Phase 3 winner, no retraining.
    split = build_classification_dataset(features_df, targets_df, target_col)
    model_a = CatBoostClassifier()
    model_a.load_model(model_a_path)
    X_val_a = split.val[full_feature_cols]
    y_val = split.val[target_col].to_numpy()
    proba_a = model_a.predict_proba(X_val_a)[:, 1]
    metrics_a = evaluate_classifier("model_a_full_spatial", y_val, proba_a)

    # Model B: ONE new training run, h3_cell/geohash removed.
    split_b = build_classification_dataset(features_df, targets_df, target_col, NUMERIC_FEATURES, REDUCED_SPATIAL_CATEGORICAL_FEATURES)
    X_train_b = split_b.train[reduced_feature_cols]
    y_train_b = split_b.train[target_col].to_numpy()
    model_b = train_catboost(X_train_b, y_train_b, REDUCED_SPATIAL_CATEGORICAL_FEATURES)
    X_val_b = split_b.val[reduced_feature_cols]
    proba_b = model_b.predict_proba(X_val_b)[:, 1]
    metrics_b = evaluate_classifier("model_b_reduced_spatial", split_b.val[target_col].to_numpy(), proba_b)

    pr_auc_drop_pct = (metrics_a.pr_auc - metrics_b.pr_auc) / metrics_a.pr_auc * 100
    verdict = "PASS" if pr_auc_drop_pct <= PR_AUC_DROP_PASS_THRESHOLD_PCT else "FAIL"

    return {
        "model_a": metrics_a.to_dict(),
        "model_b": metrics_b.to_dict(),
        "pr_auc_drop_pct": pr_auc_drop_pct,
        "verdict": f"Spatial abstraction = {verdict}",
        "removed_features": ["h3_cell", "geohash"],
        "kept_features": reduced_feature_cols,
    }
