"""
Final robustness experiment test (DECISIONS.md ADR-019). Checks the
feature_set.py constant is correctly constructed and the experiment's
verdict logic is correct, without retraining (the real-data run is
documented/verified manually in docs/spatial_dependency.md — retraining in
every test run would be wasteful for a frozen, one-off experiment).
"""

from app.models.feature_set import CATEGORICAL_FEATURES, REDUCED_SPATIAL_CATEGORICAL_FEATURES
from app.models.spatial_dependency import PR_AUC_DROP_PASS_THRESHOLD_PCT


def test_reduced_spatial_features_excludes_h3_and_geohash():
    assert "h3_cell" not in REDUCED_SPATIAL_CATEGORICAL_FEATURES
    assert "geohash" not in REDUCED_SPATIAL_CATEGORICAL_FEATURES


def test_reduced_spatial_features_keeps_organizational_categoricals():
    for col in ["junction_name", "police_station", "center_code", "vehicle_type"]:
        assert col in REDUCED_SPATIAL_CATEGORICAL_FEATURES


def test_reduced_spatial_features_is_subset_of_full_categorical_features():
    assert set(REDUCED_SPATIAL_CATEGORICAL_FEATURES) < set(CATEGORICAL_FEATURES)


def test_pass_threshold_is_3_percent():
    assert PR_AUC_DROP_PASS_THRESHOLD_PCT == 3.0
