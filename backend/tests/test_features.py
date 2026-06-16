"""
Phase 2 tests. Two kinds:
1. Leakage-safety: brute-force re-derive a handful of rolling/aggregated
   features on small synthetic data and assert the vectorized implementation
   matches — and explicitly assert "self" is never counted.
2. Real-data smoke test: the full pipeline runs end-to-end on the actual
   dataset without errors and produces sane shapes/ranges.
"""

import pandas as pd
import pytest

from app.features.aggregated import add_historical_risk_features
from app.features.build_features import build_feature_table
from app.features.outliers import flag_outlier_coordinates
from app.features.rolling import add_rolling_window_counts
from app.features.spatial import add_h3_geohash, add_spatial_density_features
from app.features.targets import add_targets
from app.features.temporal import add_calendar_features
from app.ingestion.load_data import load_raw_violations


def _make_synthetic_df():
    """4 events: 3 in cell A close together, 1 in cell A far later, 1 in cell B."""
    base = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    return pd.DataFrame({
        "id": ["e1", "e2", "e3", "e4", "e5"],
        "latitude": [12.97, 12.97, 12.97, 12.97, 12.90],
        "longitude": [77.59, 77.59, 77.59, 77.59, 77.60],
        "created_datetime": [
            base,
            base + pd.Timedelta(minutes=10),
            base + pd.Timedelta(minutes=20),
            base + pd.Timedelta(hours=5),
            base + pd.Timedelta(minutes=5),
        ],
        "junction_name": ["J1", "J1", "J2", "J1", "J3"],
        "police_station": ["P1", "P1", "P1", "P1", "P2"],
    })


def test_h3_is_deterministic_and_groups_nearby_points():
    df = _make_synthetic_df()
    df = add_h3_geohash(df)
    # First 4 rows are the same exact lat/lon -> same h3 cell.
    assert df["h3_cell"].iloc[0] == df["h3_cell"].iloc[1] == df["h3_cell"].iloc[3]
    # The 5th row (different coords) is a different cell.
    assert df["h3_cell"].iloc[4] != df["h3_cell"].iloc[0]


def test_hotspot_frequency_excludes_self_and_future():
    df = _make_synthetic_df()
    df = add_h3_geohash(df)
    df = add_spatial_density_features(df)
    # e1: first event in its cell -> 0 prior events.
    assert df.loc[df["id"] == "e1", "hotspot_frequency"].item() == 0
    # e3: third event in cell A (e1, e2 before it) -> 2 prior events.
    assert df.loc[df["id"] == "e3", "hotspot_frequency"].item() == 2
    # e4: 4th event in cell A, 5 hours later -> 3 prior events (e1,e2,e3), not 4.
    assert df.loc[df["id"] == "e4", "hotspot_frequency"].item() == 3


def test_rolling_window_count_matches_brute_force():
    df = _make_synthetic_df()
    df = add_h3_geohash(df)
    df = add_rolling_window_counts(df)

    # Brute-force: for each row, count other same-cell rows strictly within
    # (t - 15min, t), i.e. NOT including t itself.
    for _, row in df.iterrows():
        same_cell = df[df["h3_cell"] == row["h3_cell"]]
        window_start = row["created_datetime"] - pd.Timedelta(minutes=15)
        brute = ((same_cell["created_datetime"] > window_start) &
                  (same_cell["created_datetime"] < row["created_datetime"])).sum()
        assert df.loc[df["id"] == row["id"], "violations_last_15m"].item() == brute, (
            f"mismatch for {row['id']}"
        )

    # e4 (5h after the cluster) should see 0 violations in the last 15m.
    assert df.loc[df["id"] == "e4", "violations_last_15m"].item() == 0


def test_target_count_looks_forward_and_excludes_self():
    df = _make_synthetic_df()
    df = add_h3_geohash(df)
    targets = add_targets(df)

    # e1 at t=0: e2 (+10m) and e3 (+20m) fall within the next 30 minutes, e4 (+5h) does not.
    e1_target_30m = targets.loc[df["id"] == "e1", "target_count_30m"].item()
    assert e1_target_30m == 2

    # e4 (5h after the cluster, last event in its cell) has nothing after it.
    e4_target_60m = targets.loc[df["id"] == "e4", "target_count_60m"].item()
    assert e4_target_60m == 0


def test_historical_risk_is_zero_on_first_occurrence():
    df = _make_synthetic_df()
    df["primary_offence_code"] = ["O1", "O1", "O2", "O1", "O3"]
    df["vehicle_type"] = ["CAR"] * 5
    df["center_code"] = ["1"] * 5
    df = add_historical_risk_features(df)
    # The very first row overall has no prior history at all -> risk 0.
    assert df.loc[df["id"] == "e1", "junction_historical_risk"].item() == 0.0


def test_outlier_flag_catches_out_of_bbox_points():
    df = _make_synthetic_df()
    df.loc[df["id"] == "e5", "latitude"] = 40.0  # New York
    df.loc[df["id"] == "e5", "longitude"] = -74.0
    df = flag_outlier_coordinates(df)
    assert df.loc[df["id"] == "e5", "is_outlier_coordinate"].item() is True
    assert df.loc[df["id"] == "e1", "is_outlier_coordinate"].item() is False


def test_calendar_features_basic_correctness():
    df = _make_synthetic_df()
    df = add_calendar_features(df)
    assert df["hour"].iloc[0] == 0
    assert df["weekday"].iloc[0] == 0  # 2024-01-01 is a Monday
    assert not df["is_weekend"].iloc[0]


@pytest.mark.slow
def test_full_pipeline_runs_on_real_dataset():
    """End-to-end smoke test against the real CSV (slower — full 298k rows)."""
    raw = load_raw_violations()
    features = build_feature_table(raw)
    targets = add_targets(features)

    assert len(features) > 0
    assert len(features) == len(targets)
    assert features["hotspot_frequency"].min() >= 0
    assert features["is_outlier_coordinate"].sum() > 0  # we know there are some
    assert targets["target_count_60m"].min() >= 0
    # Resolution time is documented as 100% missing in this dataset (ADR/operational.py docstring).
    assert features["resolution_time_minutes"].isna().all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
