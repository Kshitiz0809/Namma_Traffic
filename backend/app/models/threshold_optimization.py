"""
Phase 3.5 Task 1 — cost-aware threshold optimization.

Replaces the F1-only operating point (Phase 3) with an explicit cost model:
    cost = FP * cost_fp + FN * cost_fn

Default cost_fn=3, cost_fp=1 encodes "missing a real hotspot is 3x worse
than a wasted patrol" — a stated assumption, not a learned one (see
DECISIONS.md ADR-014 for why and how Phase 6 should revisit it with real
intervention-cost data).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

DEFAULT_COST_FP = 1.0
DEFAULT_COST_FN = 3.0


def compute_threshold_metrics(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    thresholds: np.ndarray | None = None,
    cost_fp: float = DEFAULT_COST_FP,
    cost_fn: float = DEFAULT_COST_FN,
) -> pd.DataFrame:
    if thresholds is None:
        thresholds = np.round(np.arange(0.05, 0.951, 0.05), 2)

    rows = []
    n = len(y_true)
    for t in thresholds:
        y_pred = (y_proba >= t).astype(int)
        tp = int(np.sum((y_pred == 1) & (y_true == 1)))
        tn = int(np.sum((y_pred == 0) & (y_true == 0)))
        fp = int(np.sum((y_pred == 1) & (y_true == 0)))
        fn = int(np.sum((y_pred == 0) & (y_true == 1)))

        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        cost = fp * cost_fp + fn * cost_fn

        rows.append({
            "threshold": t, "precision": precision, "recall": recall, "f1": f1,
            "specificity": specificity, "fpr": fpr, "tp": tp, "tn": tn, "fp": fp,
            "fn": fn, "cost": cost, "cost_per_1000": cost / n * 1000,
        })

    return pd.DataFrame(rows)


def recommend_thresholds(metrics_df: pd.DataFrame) -> dict:
    """Three named operating points, each with its rationale:
    - f1: maximizes F1 (Phase 3's original criterion, kept for comparison)
    - high_precision: lowest cost among thresholds with precision >= 0.85
      (minimize false alarms for contexts where patrol capacity is scarce)
    - balanced: minimizes total intervention cost (the new default — directly
      optimizes the stated cost model rather than a proxy metric like F1)
    """
    f1_row = metrics_df.loc[metrics_df["f1"].idxmax()]

    high_precision_candidates = metrics_df[metrics_df["precision"] >= 0.85]
    high_precision_row = (
        high_precision_candidates.loc[high_precision_candidates["cost"].idxmin()]
        if len(high_precision_candidates) > 0
        else metrics_df.loc[metrics_df["precision"].idxmax()]
    )

    balanced_row = metrics_df.loc[metrics_df["cost"].idxmin()]

    return {
        "f1_threshold": {
            "threshold": float(f1_row["threshold"]), "f1": float(f1_row["f1"]),
            "precision": float(f1_row["precision"]), "recall": float(f1_row["recall"]),
            "cost": float(f1_row["cost"]),
            "rationale": "Maximizes F1 — Phase 3's original criterion, kept here for comparison.",
        },
        "high_precision_threshold": {
            "threshold": float(high_precision_row["threshold"]), "f1": float(high_precision_row["f1"]),
            "precision": float(high_precision_row["precision"]), "recall": float(high_precision_row["recall"]),
            "cost": float(high_precision_row["cost"]),
            "rationale": "Lowest-cost threshold among those with precision >= 0.85 — for patrol-capacity-constrained deployments.",
        },
        "balanced_threshold": {
            "threshold": float(balanced_row["threshold"]), "f1": float(balanced_row["f1"]),
            "precision": float(balanced_row["precision"]), "recall": float(balanced_row["recall"]),
            "cost": float(balanced_row["cost"]),
            "rationale": f"Minimizes total intervention cost (FP*{DEFAULT_COST_FP} + FN*{DEFAULT_COST_FN}) — the new recommended default.",
        },
    }
