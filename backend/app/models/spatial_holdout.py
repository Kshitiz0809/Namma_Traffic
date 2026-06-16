"""
Phase 3.5 Task 3 — spatial generalization test.

Verifies the model isn't just memorizing per-cell identity (`h3_cell` was
the #1 SHAP feature in Phase 3 — exactly the kind of result that warrants
this check). Splits H3 cells themselves (not rows) into train-cells /
holdout-cells, retrains on train-cells only, then compares PR-AUC on
seen-region rows vs. unseen-region rows from the SAME (validation) time
window — isolating the spatial effect from the temporal one, since both
evaluation sets share the same time period and only differ in whether the
model saw that specific h3_cell during training.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.classifier import build_classification_dataset, evaluate_classifier, train_catboost
from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES

HOLDOUT_FRAC = 0.20
SEED = 42


def split_cells(all_cells: np.ndarray, holdout_frac: float = HOLDOUT_FRAC, seed: int = SEED) -> tuple[set, set]:
    rng = np.random.RandomState(seed)
    shuffled = rng.permutation(all_cells)
    n_holdout = int(len(shuffled) * holdout_frac)
    holdout_cells = set(shuffled[:n_holdout])
    train_cells = set(shuffled[n_holdout:])
    return train_cells, holdout_cells


def run_spatial_holdout_test(
    features_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    target_col: str = "target_hotspot_60m",
) -> dict:
    split = build_classification_dataset(features_df, targets_df, target_col)
    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES

    all_cells = split.train["h3_cell"].unique()
    train_cells, holdout_cells = split_cells(all_cells)

    train_rows = split.train[split.train["h3_cell"].isin(train_cells)]
    X_train = train_rows[feature_cols]
    y_train = train_rows[target_col].to_numpy()

    model = train_catboost(X_train, y_train, CATEGORICAL_FEATURES)

    seen_rows = split.val[split.val["h3_cell"].isin(train_cells)]
    unseen_rows = split.val[split.val["h3_cell"].isin(holdout_cells)]

    seen_metrics = evaluate_classifier(
        "seen_regions", seen_rows[target_col].to_numpy(),
        model.predict_proba(seen_rows[feature_cols])[:, 1],
    )
    unseen_metrics = evaluate_classifier(
        "unseen_regions", unseen_rows[target_col].to_numpy(),
        model.predict_proba(unseen_rows[feature_cols])[:, 1],
    )

    pr_auc_drop_pct = (seen_metrics.pr_auc - unseen_metrics.pr_auc) / seen_metrics.pr_auc * 100
    verdict = "PASS" if pr_auc_drop_pct < 5.0 else "FAIL — recommend feature redesign"

    return {
        "n_train_cells": len(train_cells),
        "n_holdout_cells": len(holdout_cells),
        "n_seen_rows": len(seen_rows),
        "n_unseen_rows": len(unseen_rows),
        "seen_metrics": seen_metrics.to_dict(),
        "unseen_metrics": unseen_metrics.to_dict(),
        "pr_auc_drop_pct": pr_auc_drop_pct,
        "verdict": verdict,
    }
