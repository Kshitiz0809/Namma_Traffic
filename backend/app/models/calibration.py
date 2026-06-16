"""
Phase 3.5 Task 2 — probability calibration.

Calibrators are fit on the VALIDATION set against the already-trained
(Phase 3) CatBoost model (`cv="prefit"` — no base-model retraining), then
evaluated on the TEST set. See DECISIONS.md ADR-015 for the test-set-reuse
policy this and the other Phase 3.5 diagnostics rely on: test is reused
read-only for evaluation across these hardening tasks, but never used to
pick or tune the underlying model — that decision was already made (and
fixed) in Phase 3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import average_precision_score, brier_score_loss


def expected_calibration_error(y_true: np.ndarray, y_proba: np.ndarray, n_bins: int = 10) -> float:
    """Standard ECE: bin predictions into `n_bins` equal-width bins, weight
    each bin's |mean predicted prob - empirical positive rate| by bin size.
    """
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.clip(np.digitize(y_proba, bin_edges) - 1, 0, n_bins - 1)

    ece = 0.0
    n = len(y_true)
    for b in range(n_bins):
        mask = bin_idx == b
        if not mask.any():
            continue
        bin_confidence = y_proba[mask].mean()
        bin_accuracy = y_true[mask].mean()
        ece += (mask.sum() / n) * abs(bin_confidence - bin_accuracy)
    return float(ece)


def fit_calibrators(model, X_val, y_val) -> dict:
    # FrozenEstimator marks `model` as already-fitted so CalibratedClassifierCV
    # only fits the calibration mapping (on X_val/y_val), never refits the
    # base model — the sklearn >=1.6 replacement for the removed cv="prefit".
    frozen = FrozenEstimator(model)

    platt = CalibratedClassifierCV(estimator=frozen, method="sigmoid")
    platt.fit(X_val, y_val)

    isotonic = CalibratedClassifierCV(estimator=frozen, method="isotonic")
    isotonic.fit(X_val, y_val)

    return {"platt": platt, "isotonic": isotonic}


def compare_calibration_methods(model, X_val, y_val, X_test, y_test) -> pd.DataFrame:
    calibrators = fit_calibrators(model, X_val, y_val)

    baseline_proba = model.predict_proba(X_test)[:, 1]
    rows = [_score_row("baseline", y_test, baseline_proba, baseline_proba)]

    for name, calibrator in calibrators.items():
        proba = calibrator.predict_proba(X_test)[:, 1]
        rows.append(_score_row(name, y_test, proba, baseline_proba))

    return pd.DataFrame(rows)


def _score_row(name: str, y_true: np.ndarray, y_proba: np.ndarray, baseline_proba: np.ndarray) -> dict:
    brier = brier_score_loss(y_true, y_proba)
    baseline_brier = brier_score_loss(y_true, baseline_proba)
    pr_auc = average_precision_score(y_true, y_proba)
    baseline_pr_auc = average_precision_score(y_true, baseline_proba)
    ece = expected_calibration_error(y_true, y_proba)

    return {
        "method": name,
        "brier_score": brier,
        "brier_improvement_pct": 0.0 if name == "baseline" else (baseline_brier - brier) / baseline_brier * 100,
        "ece": ece,
        "pr_auc": pr_auc,
        "pr_auc_delta_pct": 0.0 if name == "baseline" else (pr_auc - baseline_pr_auc) / baseline_pr_auc * 100,
    }


def decide_calibration(results_df: pd.DataFrame, min_brier_improvement_pct: float = 5.0, max_pr_auc_drop_pct: float = 1.0) -> dict:
    """Acceptance rule: choose a calibrated method only if Brier improves
    >=5% AND PR-AUC drop <1% vs. baseline. Otherwise keep baseline (uncalibrated).
    """
    candidates = results_df[results_df["method"] != "baseline"].copy()
    eligible = candidates[
        (candidates["brier_improvement_pct"] >= min_brier_improvement_pct)
        & (candidates["pr_auc_delta_pct"] > -max_pr_auc_drop_pct)
    ]

    if len(eligible) == 0:
        return {
            "chosen_method": "baseline",
            "reason": f"No calibration method met the bar (Brier improvement >= {min_brier_improvement_pct}% "
                      f"and PR-AUC drop < {max_pr_auc_drop_pct}%). Keeping uncalibrated probabilities.",
        }

    best = eligible.loc[eligible["brier_improvement_pct"].idxmax()]
    return {
        "chosen_method": best["method"],
        "reason": f"{best['method']} improved Brier by {best['brier_improvement_pct']:.2f}% "
                  f"with a PR-AUC change of {best['pr_auc_delta_pct']:.2f}% — meets the acceptance bar.",
    }
