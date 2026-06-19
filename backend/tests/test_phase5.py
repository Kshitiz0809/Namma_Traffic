"""
Phase 5 tests: risk_score math, recommendation rule engine (incl. the
"No Junction" data-quirk exclusion), alert generation, and the forecast
API (via FastAPI TestClient, no live server needed). No retraining --
frozen models loaded as-is.
"""

import numpy as np
import pandas as pd
import pytest

from app.models.alerts import ALERT_COLOR_BY_BAND, generate_alerts
from app.models.recommendation import (
    classify_vehicle_mix,
    compute_junction_history_flag,
    load_rules,
    recommend,
)
from app.models.risk_score import RiskParams, assign_risk_band, compute_risk_score

EQUAL_WEIGHTS = {
    "hotspot_probability": 0.40,
    "normalized_predicted_count": 0.30,
    "persistence": 0.20,
    "recent_intensity": 0.10,
}


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def _make_features_df(n=3):
    return pd.DataFrame({
        "rolling_hotspot_intensity": [0.0, 5.0, 10.0][:n],
        "violations_last_15m": [0.0, 5.0, 10.0][:n],
    })


def test_assign_risk_band_boundaries():
    cutoffs = [34.0, 45.1, 54.2]
    assert assign_risk_band(0.0, cutoffs) == "LOW"
    assert assign_risk_band(33.99, cutoffs) == "LOW"
    assert assign_risk_band(34.0, cutoffs) == "MEDIUM"
    assert assign_risk_band(45.1, cutoffs) == "HIGH"
    assert assign_risk_band(54.2, cutoffs) == "CRITICAL"
    assert assign_risk_band(100.0, cutoffs) == "CRITICAL"


def test_compute_risk_score_max_inputs_gives_100():
    params = RiskParams(
        weights=EQUAL_WEIGHTS, band_cutoffs=[34.0, 45.1, 54.2],
        predicted_count_min=0.0, predicted_count_max=10.0,
        rolling_intensity_min=0.0, rolling_intensity_max=10.0,
        recent_intensity_min=0.0, recent_intensity_max=10.0,
    )
    features = _make_features_df(1)
    features.loc[0, ["rolling_hotspot_intensity", "violations_last_15m"]] = [10.0, 10.0]
    risk_df = compute_risk_score(
        hotspot_probability=np.array([1.0]), predicted_count=np.array([10.0]),
        features=features, params=params,
    )
    assert risk_df["risk_score"].iloc[0] == 100.0
    assert risk_df["risk_band"].iloc[0] == "CRITICAL"


def test_compute_risk_score_min_inputs_gives_zero():
    params = RiskParams(
        weights=EQUAL_WEIGHTS, band_cutoffs=[34.0, 45.1, 54.2],
        predicted_count_min=0.0, predicted_count_max=10.0,
        rolling_intensity_min=0.0, rolling_intensity_max=10.0,
        recent_intensity_min=0.0, recent_intensity_max=10.0,
    )
    features = _make_features_df(1)
    features.loc[0, ["rolling_hotspot_intensity", "violations_last_15m"]] = [0.0, 0.0]
    risk_df = compute_risk_score(
        hotspot_probability=np.array([0.0]), predicted_count=np.array([0.0]),
        features=features, params=params,
    )
    assert risk_df["risk_score"].iloc[0] == 0.0
    assert risk_df["risk_band"].iloc[0] == "LOW"


def test_compute_risk_score_clips_out_of_range_predicted_count():
    params = RiskParams(
        weights=EQUAL_WEIGHTS, band_cutoffs=[34.0, 45.1, 54.2],
        predicted_count_min=0.0, predicted_count_max=10.0,
        rolling_intensity_min=0.0, rolling_intensity_max=10.0,
        recent_intensity_min=0.0, recent_intensity_max=10.0,
    )
    features = _make_features_df(1)
    features.loc[0, ["rolling_hotspot_intensity", "violations_last_15m"]] = [0.0, 0.0]
    risk_df = compute_risk_score(
        hotspot_probability=np.array([0.0]), predicted_count=np.array([999.0]),  # way beyond train max
        features=features, params=params,
    )
    assert risk_df["normalized_predicted_count"].iloc[0] == 1.0  # clipped, not extrapolated


def test_classify_vehicle_mix(rules):
    assert classify_vehicle_mix("LORRY/GOODS VEHICLE", rules) == "high_obstruction"
    assert classify_vehicle_mix("CAR", rules) == "low_obstruction"
    assert classify_vehicle_mix("SOMETHING_NOT_IN_EITHER_LIST", rules) == "unknown"


def test_junction_history_flag_excludes_no_junction_quirk(rules):
    # Even with a high junction_historical_risk value, "No Junction" never flags --
    # that category's high share is a data quirk (49.5% placeholder rows), not a real signal.
    assert compute_junction_history_flag("No Junction", 0.5, rules) is False
    assert compute_junction_history_flag("BTP051 - Safina Plaza Junction", 0.5, rules) is True
    assert compute_junction_history_flag("BTP051 - Safina Plaza Junction", 0.01, rules) is False


def test_recommend_escalates_medium_to_high_with_obstruction_and_history(rules):
    rec = recommend("MEDIUM", "LORRY/GOODS VEHICLE", "BTP051 - Safina Plaza Junction", 0.06, rules)
    assert rec.escalated is True
    assert rec.risk_band == "HIGH"
    assert rec.final_action == "Deploy enforcement"


def test_recommend_does_not_escalate_with_low_obstruction_vehicle(rules):
    rec = recommend("MEDIUM", "CAR", "BTP051 - Safina Plaza Junction", 0.06, rules)
    assert rec.escalated is False
    assert rec.risk_band == "MEDIUM"
    assert rec.final_action == "Patrol"


def test_recommend_never_escalates_no_junction_even_with_obstruction_vehicle(rules):
    rec = recommend("MEDIUM", "LORRY/GOODS VEHICLE", "No Junction", 0.5, rules)
    assert rec.escalated is False  # "No Junction" excluded regardless of vehicle mix


def test_alert_color_mapping_matches_risk_bands():
    assert ALERT_COLOR_BY_BAND == {"LOW": "GREEN", "MEDIUM": "YELLOW", "HIGH": "ORANGE", "CRITICAL": "RED"}


def test_generate_alerts_respects_max_per_band_and_min_band():
    risk_df = pd.DataFrame({
        "h3_cell": [f"cell_{i}" for i in range(10)],
        "junction_name": ["J1"] * 10,
        "created_datetime": pd.Timestamp("2024-01-01", tz="UTC"),
        "hotspot_probability": np.linspace(0.5, 0.9, 10),
        "risk_score": np.linspace(40, 60, 10),
        "contribution_hotspot_probability": [10.0] * 10,
        "contribution_normalized_predicted_count": [5.0] * 10,
        "contribution_persistence": [3.0] * 10,
        "contribution_recent_intensity": [1.0] * 10,
    })

    class FakeRec:
        def __init__(self, band, action):
            self.risk_band = band
            self.final_action = action

    recs = [FakeRec("MEDIUM" if s < 45.1 else "HIGH", "Patrol" if s < 45.1 else "Deploy enforcement")
            for s in risk_df["risk_score"]]

    alerts = generate_alerts(risk_df, recs, min_band="MEDIUM", max_per_band=2)
    assert len(alerts) <= 4  # at most 2 per band, 2 bands present
    for alert in alerts:
        assert alert["alert_level"] in {"YELLOW", "ORANGE"}
        assert len(alert["top_contributing_factors"]) == 2


@pytest.mark.slow
def test_forecast_endpoint_via_testclient():
    """Real-data smoke test for the live API, using frozen models."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # A known cell from the real dataset.
    r = client.get("/forecast", params={"h3_cell": "89618925c03ffff"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_cold_start"] is False
    assert 0.0 <= body["hotspot_probability"] <= 1.0
    assert 0.0 <= body["congestion_risk"] <= 100.0
    assert body["recommendation"] in {"Monitor", "Patrol", "Deploy enforcement", "Tow operation candidate"}

    # Cold start.
    r2 = client.get("/forecast", params={"h3_cell": "ffffffffffffff"})
    assert r2.status_code == 200
    assert r2.json()["is_cold_start"] is True

    # Missing params.
    r3 = client.get("/forecast")
    assert r3.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
