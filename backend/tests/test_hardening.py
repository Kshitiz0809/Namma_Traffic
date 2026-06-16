"""
Phase 3.5/4 hardening tests — fast unit tests on synthetic data for the
math/logic in threshold_optimization.py, calibration.py, spatial_holdout.py,
multi_horizon.py, shap_audit.py. No retraining here (that's the slow
real-data smoke tests in test_models.py) — these check the formulas and
decision rules are correct in isolation.
"""

import numpy as np
import pandas as pd
import pytest

from app.models.calibration import decide_calibration, expected_calibration_error
from app.models.multi_horizon import recommend_horizon
from app.models.shap_audit import compute_rank_stability
from app.models.spatial_holdout import split_cells
from app.models.threshold_optimization import compute_threshold_metrics, recommend_thresholds


def test_threshold_metrics_cost_formula():
    # 4 points: at threshold 0.5, 1 FP and 1 FN.
    y_true = np.array([0, 0, 1, 1])
    y_proba = np.array([0.1, 0.6, 0.4, 0.9])
    df = compute_threshold_metrics(y_true, y_proba, thresholds=np.array([0.5]), cost_fp=1.0, cost_fn=3.0)

    row = df.iloc[0]
    assert row["fp"] == 1
    assert row["fn"] == 1
    assert row["cost"] == 1 * 1.0 + 1 * 3.0


def test_threshold_metrics_specificity_and_fpr_complement():
    y_true = np.array([0, 0, 0, 1, 1])
    y_proba = np.array([0.1, 0.2, 0.8, 0.6, 0.9])
    df = compute_threshold_metrics(y_true, y_proba, thresholds=np.array([0.5]))
    row = df.iloc[0]
    assert abs(row["specificity"] + row["fpr"] - 1.0) < 1e-9


def test_recommend_thresholds_balanced_is_global_min_cost():
    rng = np.random.RandomState(0)
    y_true = np.array([0] * 70 + [1] * 30)
    y_proba = np.concatenate([rng.uniform(0.0, 0.6, 70), rng.uniform(0.4, 0.9, 30)])
    df = compute_threshold_metrics(y_true, y_proba)
    recs = recommend_thresholds(df)
    balanced_cost = recs["balanced_threshold"]["cost"]
    assert balanced_cost == df["cost"].min()
    assert set(recs.keys()) == {"f1_threshold", "high_precision_threshold", "balanced_threshold"}


def test_expected_calibration_error_zero_when_perfectly_calibrated():
    # 10 items per bin, predicted prob == empirical accuracy exactly.
    y_true = np.array([0] * 9 + [1] * 1)  # 10% positive
    y_proba = np.full(10, 0.1)  # predicts exactly 10% for all -> ECE should be 0
    ece = expected_calibration_error(y_true, y_proba, n_bins=10)
    assert ece < 1e-9


def test_expected_calibration_error_positive_when_miscalibrated():
    y_true = np.array([0] * 5 + [1] * 5)
    y_proba = np.full(10, 0.9)  # predicts 90% positive but only 50% are
    ece = expected_calibration_error(y_true, y_proba, n_bins=10)
    assert ece > 0.3


def test_decide_calibration_rejects_below_threshold():
    df = pd.DataFrame({
        "method": ["baseline", "platt", "isotonic"],
        "brier_improvement_pct": [0.0, 1.0, 2.0],  # below 5% bar
        "pr_auc_delta_pct": [0.0, 0.0, -0.2],
    })
    decision = decide_calibration(df)
    assert decision["chosen_method"] == "baseline"


def test_decide_calibration_accepts_when_criteria_met():
    df = pd.DataFrame({
        "method": ["baseline", "platt", "isotonic"],
        "brier_improvement_pct": [0.0, 6.0, 2.0],
        "pr_auc_delta_pct": [0.0, -0.5, -0.2],
    })
    decision = decide_calibration(df)
    assert decision["chosen_method"] == "platt"


def test_split_cells_disjoint_and_proportioned():
    cells = np.array([f"cell_{i}" for i in range(100)])
    train_cells, holdout_cells = split_cells(cells, holdout_frac=0.2, seed=1)
    assert len(train_cells & holdout_cells) == 0
    assert len(holdout_cells) == 20
    assert len(train_cells) == 80


def test_split_cells_deterministic_with_seed():
    cells = np.array([f"cell_{i}" for i in range(50)])
    a_train, a_holdout = split_cells(cells, seed=7)
    b_train, b_holdout = split_cells(cells, seed=7)
    assert a_train == b_train
    assert a_holdout == b_holdout


def test_recommend_horizon_picks_highest_lift_not_highest_pr_auc():
    df = pd.DataFrame({
        "horizon_minutes": [15, 30, 60, 90],
        "pr_auc": [0.70, 0.80, 0.85, 0.90],
        "positive_rate": [0.50, 0.65, 0.72, 0.80],  # lift: 1.4, 1.231, 1.181, 1.125
    })
    df["lift_over_base_rate"] = df["pr_auc"] / df["positive_rate"]
    rec = recommend_horizon(df)
    assert rec["recommended_horizon_minutes"] == 15  # highest lift despite lowest raw PR-AUC


def test_compute_rank_stability_perfect_when_identical_across_bootstraps():
    importance = pd.DataFrame({
        "bootstrap_0": [0.5, 0.3, 0.1],
        "bootstrap_1": [0.5, 0.3, 0.1],
    }, index=["feat_a", "feat_b", "feat_c"])
    result = compute_rank_stability(importance, top_n=2)
    assert result["stability_score"] == 1.0
    assert set(result["always_in_top_n"]) == {"feat_a", "feat_b"}


def test_compute_rank_stability_imperfect_when_rankings_differ():
    importance = pd.DataFrame({
        "bootstrap_0": [0.9, 0.1, 0.05],
        "bootstrap_1": [0.05, 0.1, 0.9],
    }, index=["feat_a", "feat_b", "feat_c"])
    result = compute_rank_stability(importance, top_n=1)
    # top-1 in bootstrap_0 is feat_a, top-1 in bootstrap_1 is feat_c -> disjoint -> stability 0
    assert result["stability_score"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
