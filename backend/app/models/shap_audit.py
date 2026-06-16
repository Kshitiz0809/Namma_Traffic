"""
Phase 3.5/4 Task 5 — explainability audit.

Re-runs SHAP across multiple bootstrap resamples of the validation set to
check whether the top-feature ranking is stable (not an artifact of one
particular sample), and explicitly checks for the failure modes the task
named: H3 dominance, timestamp leakage, unstable features, target proxies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.explain import compute_shap_values, shap_feature_importance
from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES

N_BOOTSTRAPS = 5
BOOTSTRAP_SAMPLE_FRAC = 0.5
TARGET_PROXY_CORR_THRESHOLD = 0.95
TOP_N_FOR_STABILITY = 10


def bootstrap_shap_importance(model, X: pd.DataFrame, n_bootstraps: int = N_BOOTSTRAPS, seed: int = 42) -> pd.DataFrame:
    """Returns a DataFrame: rows=features, columns=bootstrap_0..N, values=mean|SHAP|."""
    rng = np.random.RandomState(seed)
    results = {}
    for i in range(n_bootstraps):
        sample = X.sample(frac=BOOTSTRAP_SAMPLE_FRAC, random_state=rng.randint(0, 1_000_000))
        shap_values, X_sample = compute_shap_values(model, sample, max_samples=len(sample))
        importance = shap_feature_importance(shap_values, list(X.columns))
        results[f"bootstrap_{i}"] = importance.set_index("feature")["mean_abs_shap"]

    return pd.DataFrame(results)


def compute_rank_stability(importance_table: pd.DataFrame, top_n: int = TOP_N_FOR_STABILITY) -> dict:
    """For each bootstrap, get its top-N feature set; stability = how
    consistently the SAME features appear in every bootstrap's top-N
    (Jaccard-style: intersection / union across all bootstrap top-N sets).
    """
    top_sets = [
        set(importance_table[col].nlargest(top_n).index)
        for col in importance_table.columns
    ]
    intersection = set.intersection(*top_sets)
    union = set.union(*top_sets)
    stability_score = len(intersection) / len(union) if union else 0.0

    rank_std = importance_table.rank(ascending=False).std(axis=1).sort_values(ascending=False)

    return {
        "stability_score": stability_score,  # 1.0 = identical top-N every time
        "always_in_top_n": sorted(intersection),
        "sometimes_in_top_n": sorted(union - intersection),
        "highest_rank_variance_features": rank_std.head(5).to_dict(),
    }


def detect_target_proxies(
    features_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    target_col: str = "target_hotspot_60m",
    threshold: float = TARGET_PROXY_CORR_THRESHOLD,
) -> list[str]:
    """Flags any numeric feature suspiciously close to a 1:1 proxy for the
    target (correlation >= threshold) — would indicate a leakage bug, not a
    genuinely strong feature (genuinely strong features here top out around
    0.3-0.4 correlation per Phase 2's feature validation notebook).
    """
    joined = features_df.merge(targets_df[["id", target_col]], on="id")
    correlations = joined[NUMERIC_FEATURES + [target_col]].corr()[target_col].drop(target_col)
    return correlations[correlations.abs() >= threshold].index.tolist()


def run_explainability_audit(model, X_val: pd.DataFrame, features_df: pd.DataFrame, targets_df: pd.DataFrame) -> dict:
    importance_table = bootstrap_shap_importance(model, X_val)
    stability = compute_rank_stability(importance_table)

    # Rank each bootstrap column (axis=0) across ALL features, then read off
    # h3_cell's rank in each — NOT h3_cell's bootstrap values ranked against
    # each other (that would just always be ~mid-rank-of-5, regardless of
    # how dominant h3_cell actually is among the other 29 features).
    full_rank_table = importance_table.rank(ascending=False, axis=0)
    h3_mean_rank = float(full_rank_table.loc["h3_cell"].mean()) if "h3_cell" in full_rank_table.index else None
    h3_dominance = h3_mean_rank is not None and h3_mean_rank <= 1.5

    timestamp_leakage = any(
        col in (NUMERIC_FEATURES + CATEGORICAL_FEATURES)
        for col in ["created_datetime", "closed_datetime", "modified_datetime", "validation_timestamp"]
    )

    target_proxies = detect_target_proxies(features_df, targets_df)

    return {
        "h3_dominance": h3_dominance,
        "h3_mean_rank": h3_mean_rank,
        "timestamp_leakage_detected": timestamp_leakage,
        "target_proxies_detected": target_proxies,
        "stability": stability,
        "importance_table": importance_table,
    }
