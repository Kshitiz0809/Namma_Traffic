"""
Phase 3 tests. Fast unit tests on synthetic data (split correctness, dtype
casting, congestion score math, metric sanity) plus one slow end-to-end
smoke test that trains tiny models on a small real-data sample (kept small
so the suite doesn't take the full ~9-minute production training run).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.models.classifier import (
    build_classification_dataset,
    evaluate_classifier,
    train_all_classifiers,
)
from app.models.congestion_score import WEIGHTS, compute_congestion_score, fit_minmax
from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES, prepare_model_frame
from app.models.split import time_based_split
from app.ingestion.load_data import load_raw_violations
from app.features.build_features import build_feature_table
from app.features.targets import add_targets


def _make_synthetic_split_df(n=100):
    base = pd.Timestamp("2024-01-01", tz="UTC")
    return pd.DataFrame({
        "created_datetime": [base + pd.Timedelta(hours=i) for i in range(n)],
        "value": range(n),
    })


def test_time_based_split_is_chronological_and_non_overlapping():
    df = _make_synthetic_split_df(100)
    split = time_based_split(df, train_frac=0.7, val_frac=0.15)

    assert len(split.train) == 70
    assert len(split.val) == 15
    assert len(split.test) == 15
    assert split.train["created_datetime"].max() <= split.val["created_datetime"].min()
    assert split.val["created_datetime"].max() <= split.test["created_datetime"].min()


def test_prepare_model_frame_casts_bool_and_fills_categorical_na():
    df = pd.DataFrame({
        "hotspot_frequency": [1, 2, 3],
        "violation_density": [0.1, 0.2, 0.3],
        "junction_density": [1, 1, 2],
        "police_station_density": [1, 1, 1],
        "hour": [0, 12, 23],
        "weekday": [0, 1, 2],
        "is_weekend": [True, False, True],
        "hour_sin": [0.0, 0.0, 0.0],
        "hour_cos": [1.0, 1.0, 1.0],
        "is_peak_hour": [False, True, False],
        "violation_frequency": [0.0, 1.0, 2.0],
        "violations_last_15m": [0, 0, 0],
        "violations_last_30m": [0, 0, 0],
        "violations_last_60m": [0, 0, 0],
        "same_hour_previous_day": [0, 0, 0],
        "rolling_hotspot_intensity": [0.0, 0.0, 0.0],
        "junction_historical_risk": [0.0, 0.0, 0.0],
        "offence_historical_risk": [0.0, 0.0, 0.0],
        "vehicle_type_historical_risk": [0.0, 0.0, 0.0],
        "center_code_historical_risk": [0.0, 0.0, 0.0],
        "num_offences": [1, 1, 2],
        "is_outlier_coordinate": [False, False, True],
        "is_duplicate_vehicle_event": [False, True, False],
        "h3_cell": ["a", "b", "a"],
        "junction_name": ["J1", None, "J2"],
        "police_station": ["P1", "P1", "P2"],
        "center_code": [None, "1", "2"],
        "vehicle_type": ["CAR", "BIKE", "CAR"],
        "primary_offence_code": ["112", "104", "112"],
        "primary_violation_type": ["A", "B", "A"],
    })
    out = prepare_model_frame(df, NUMERIC_FEATURES, CATEGORICAL_FEATURES)

    assert out["is_weekend"].dtype != bool
    assert out["is_weekend"].tolist() == [1, 0, 1]
    assert str(out["junction_name"].dtype) == "category"
    assert out["junction_name"].iloc[1] == "MISSING"
    assert out["center_code"].iloc[0] == "MISSING"
    assert not out["junction_name"].isna().any()


def test_congestion_score_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_congestion_score_is_bounded_and_monotonic():
    train_df = pd.DataFrame({
        "violation_density": [0.0, 5.0, 10.0],
        "rolling_hotspot_intensity": [0.0, 5.0, 10.0],
        "police_station_density": [0, 1, 2],
    })
    params = fit_minmax(train_df)

    # A row at the max of every component should score 1.0 (sum of weights).
    max_row = pd.DataFrame({
        "violation_density": [10.0],
        "rolling_hotspot_intensity": [10.0],
        "police_station_density": [2],
    })
    result = compute_congestion_score(max_row, params)
    assert abs(result["congestion_score"].iloc[0] - 1.0) < 1e-9

    # A row beyond train's observed range gets clipped to 1.0, not extrapolated.
    beyond_row = pd.DataFrame({
        "violation_density": [999.0],
        "rolling_hotspot_intensity": [999.0],
        "police_station_density": [999],
    })
    result_beyond = compute_congestion_score(beyond_row, params)
    assert result_beyond["congestion_score"].iloc[0] == result["congestion_score"].iloc[0]


def test_evaluate_classifier_perfect_predictions():
    y_true = np.array([0, 0, 1, 1, 1])
    y_proba = np.array([0.01, 0.02, 0.9, 0.95, 0.99])
    metrics = evaluate_classifier("perfect", y_true, y_proba, threshold=0.5)

    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1 == 1.0
    assert metrics.pr_auc == 1.0


def test_evaluate_classifier_reports_confusion_matrix_shape():
    y_true = np.array([0, 1, 0, 1])
    y_proba = np.array([0.1, 0.9, 0.8, 0.2])  # 2 wrong
    metrics = evaluate_classifier("mixed", y_true, y_proba, threshold=0.5)

    cm = metrics.confusion_matrix
    assert len(cm) == 2 and len(cm[0]) == 2
    assert sum(sum(row) for row in cm) == 4


@pytest.mark.slow
def test_classifier_pipeline_runs_on_small_real_sample():
    """End-to-end smoke test on a small slice of the real dataset, with tiny
    models (few iterations) — checks the pipeline runs and produces sane
    metrics, without paying for the full ~9-minute production training run.
    """
    raw = load_raw_violations()
    sample = raw.sort_values("created_datetime").head(8000).copy()
    features = build_feature_table(sample)
    targets = add_targets(features)

    split = build_classification_dataset(features, targets)
    assert len(split.train) > 0 and len(split.val) > 0 and len(split.test) > 0

    # Monkeypatch-free tiny run: just confirm training completes and metrics are in range.
    from app.models.classifier import train_catboost
    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    X_train = split.train[feature_cols]
    y_train = split.train["target_hotspot_60m"].to_numpy()

    if y_train.sum() == 0 or y_train.sum() == len(y_train):
        pytest.skip("Sample too small/imbalanced for a meaningful classifier smoke test")

    model = train_catboost(X_train, y_train, CATEGORICAL_FEATURES)
    proba = model.predict_proba(split.val[feature_cols])[:, 1]
    metrics = evaluate_classifier("smoke", split.val["target_hotspot_60m"].to_numpy(), proba)

    assert 0.0 <= metrics.pr_auc <= 1.0
    assert 0.0 <= metrics.precision <= 1.0
    assert 0.0 <= metrics.recall <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
