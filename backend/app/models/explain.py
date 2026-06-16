"""
SHAP explainability for the winning classifier (DECISIONS.md ADR-008: SHAP
is a Phase 3 concern since it explains a trained model, not a feature table).

Uses `shap.TreeExplainer`, which works natively with CatBoost/LightGBM/XGBoost
without needing a background dataset sample (unlike KernelExplainer) — fast
and exact for tree ensembles.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import shap


def compute_shap_values(model, X: pd.DataFrame, max_samples: int = 5000) -> tuple[np.ndarray, pd.DataFrame]:
    """Returns (shap_values, X_sample) — SHAP on the full val/test set is
    unnecessary and slow; a random sample is enough for summary plots and
    global importance ranking, which is what Phase 3 needs.
    """
    if len(X) > max_samples:
        X_sample = X.sample(n=max_samples, random_state=42)
    else:
        X_sample = X

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

    # Some library/version combos return a list (per-class) for binary
    # classification; normalize to the positive-class array.
    if isinstance(shap_values, list):
        shap_values = shap_values[1]
    if shap_values.ndim == 3:  # (n_samples, n_features, n_classes)
        shap_values = shap_values[:, :, 1]

    return shap_values, X_sample


def shap_feature_importance(shap_values: np.ndarray, feature_names: list[str]) -> pd.DataFrame:
    """Mean |SHAP value| per feature — the standard global-importance ranking."""
    importance = np.abs(shap_values).mean(axis=0)
    return (
        pd.DataFrame({"feature": feature_names, "mean_abs_shap": importance})
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
