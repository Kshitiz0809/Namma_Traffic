"""
Required ablation experiments A-D (DECISIONS.md ADR-012). Each is a
single-factor change against the same baseline configuration (CatBoost,
the Phase 3 winner — see baseline_results.md), evaluated on the same
time-based validation split for comparability.

  A. with vs without is_outlier_coordinate rows
  B. with vs without is_duplicate_vehicle_event rows
  C. H3-derived vs GeoHash-derived spatial key
  D. raw counts only vs full rolling feature set
"""

from __future__ import annotations

import pandas as pd

from app.models.classifier import build_classification_dataset, evaluate_classifier, train_catboost
from app.models.feature_set import (
    CATEGORICAL_FEATURES,
    GEOHASH_CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    RAW_COUNT_ONLY_NUMERIC_FEATURES,
)


def _run_single(
    features_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    numeric_features: list[str],
    categorical_features: list[str],
    label: str,
) -> dict:
    split = build_classification_dataset(features_df, targets_df, "target_hotspot_60m", numeric_features, categorical_features)
    feature_cols = numeric_features + categorical_features
    X_train, y_train = split.train[feature_cols], split.train["target_hotspot_60m"].to_numpy()
    X_val, y_val = split.val[feature_cols], split.val["target_hotspot_60m"].to_numpy()

    model = train_catboost(X_train, y_train, categorical_features)
    proba = model.predict_proba(X_val)[:, 1]
    metrics = evaluate_classifier(label, y_val, proba)
    return metrics.to_dict()


def experiment_a_outliers(features_df: pd.DataFrame, targets_df: pd.DataFrame) -> list[dict]:
    with_outliers = _run_single(features_df, targets_df, NUMERIC_FEATURES, CATEGORICAL_FEATURES, "A.with_outliers")
    without = features_df[~features_df["is_outlier_coordinate"]]
    without_outliers = _run_single(without, targets_df, NUMERIC_FEATURES, CATEGORICAL_FEATURES, "A.without_outliers")
    return [with_outliers, without_outliers]


def experiment_b_duplicates(features_df: pd.DataFrame, targets_df: pd.DataFrame) -> list[dict]:
    with_dupes = _run_single(features_df, targets_df, NUMERIC_FEATURES, CATEGORICAL_FEATURES, "B.with_duplicates")
    without = features_df[~features_df["is_duplicate_vehicle_event"]]
    without_dupes = _run_single(without, targets_df, NUMERIC_FEATURES, CATEGORICAL_FEATURES, "B.without_duplicates")
    return [with_dupes, without_dupes]


def experiment_c_h3_vs_geohash(features_df: pd.DataFrame, targets_df: pd.DataFrame) -> list[dict]:
    h3_result = _run_single(features_df, targets_df, NUMERIC_FEATURES, CATEGORICAL_FEATURES, "C.h3_cell")
    geohash_result = _run_single(features_df, targets_df, NUMERIC_FEATURES, GEOHASH_CATEGORICAL_FEATURES, "C.geohash")
    return [h3_result, geohash_result]


def experiment_d_raw_vs_rolling(features_df: pd.DataFrame, targets_df: pd.DataFrame) -> list[dict]:
    raw_only = _run_single(features_df, targets_df, RAW_COUNT_ONLY_NUMERIC_FEATURES, CATEGORICAL_FEATURES, "D.raw_counts_only")
    full_rolling = _run_single(features_df, targets_df, NUMERIC_FEATURES, CATEGORICAL_FEATURES, "D.full_rolling")
    return [raw_only, full_rolling]


def run_all_experiments(features_df: pd.DataFrame, targets_df: pd.DataFrame) -> list[dict]:
    results = []
    results += experiment_a_outliers(features_df, targets_df)
    results += experiment_b_duplicates(features_df, targets_df)
    results += experiment_c_h3_vs_geohash(features_df, targets_df)
    results += experiment_d_raw_vs_rolling(features_df, targets_df)
    return results
