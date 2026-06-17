"""
Phase 7 tests: carriageway_impact.py math (synthetic, known answers) + the
/replay endpoint (real data, frozen models via FastAPI TestClient).
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.carriageway_impact import compute_carriageway_impact
from app.models.recommendation import load_rules

client = TestClient(app)


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def _make_features(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["created_datetime"] = pd.to_datetime(df["created_datetime"], utc=True)
    return df


def test_single_low_obstruction_vehicle_scores_one(rules):
    df = _make_features([
        {"h3_cell": "A", "vehicle_type": "CAR", "created_datetime": "2024-01-01 10:00:00"},
    ])
    out = compute_carriageway_impact(df, rules)
    assert out["carriageway_impact_score"].iloc[0] == 1.0
    assert out["carriageway_impact_label"].iloc[0] == "Minimal"


def test_concurrent_high_and_low_obstruction_vehicles_sum_weights(rules):
    # Same cell, 3 minutes apart (within the 15-minute concurrency window):
    # one LORRY (high obstruction, weight 2.0) + one CAR (weight 1.0).
    df = _make_features([
        {"h3_cell": "A", "vehicle_type": "LORRY/GOODS VEHICLE", "created_datetime": "2024-01-01 10:00:00"},
        {"h3_cell": "A", "vehicle_type": "CAR", "created_datetime": "2024-01-01 10:03:00"},
    ])
    out = compute_carriageway_impact(df, rules)
    # The second row sees both itself and the still-recent LORRY -> 2.0 + 1.0.
    second_row_score = out.sort_values("created_datetime")["carriageway_impact_score"].iloc[1]
    assert second_row_score == 3.0


def test_events_outside_window_do_not_contribute(rules):
    df = _make_features([
        {"h3_cell": "A", "vehicle_type": "LORRY/GOODS VEHICLE", "created_datetime": "2024-01-01 10:00:00"},
        {"h3_cell": "A", "vehicle_type": "CAR", "created_datetime": "2024-01-01 10:30:00"},  # 30 min later
    ])
    out = compute_carriageway_impact(df, rules)
    later_row_score = out.sort_values("created_datetime")["carriageway_impact_score"].iloc[1]
    assert later_row_score == 1.0  # only itself, the LORRY is outside the 15-min window


def test_different_cells_do_not_interfere(rules):
    df = _make_features([
        {"h3_cell": "A", "vehicle_type": "LORRY/GOODS VEHICLE", "created_datetime": "2024-01-01 10:00:00"},
        {"h3_cell": "B", "vehicle_type": "CAR", "created_datetime": "2024-01-01 10:01:00"},
    ])
    out = compute_carriageway_impact(df, rules)
    cell_b_score = out[out["h3_cell"] == "B"]["carriageway_impact_score"].iloc[0]
    assert cell_b_score == 1.0


def test_unknown_vehicle_type_defaults_to_low_obstruction(rules):
    df = _make_features([
        {"h3_cell": "A", "vehicle_type": "SUBMARINE", "created_datetime": "2024-01-01 10:00:00"},
    ])
    out = compute_carriageway_impact(df, rules)
    assert out["carriageway_impact_score"].iloc[0] == 1.0


@pytest.mark.slow
def test_replay_growth_endpoint_returns_real_sequence():
    r = client.get("/replay/growth")
    assert r.status_code == 200
    body = r.json()
    assert body["is_real_data"] is True
    assert body["scenario"] == "growth"
    assert body["point_count"] > 0
    assert len(body["points"]) == body["point_count"]
    first = body["points"][0]
    assert "carriageway_impact_score" in first
    assert "risk_score" in first
    assert "latitude" in first and "longitude" in first
    # chronological order
    timestamps = [p["timestamp"] for p in body["points"]]
    assert timestamps == sorted(timestamps)


def test_replay_unknown_scenario_returns_404():
    r = client.get("/replay/not-a-real-scenario")
    assert r.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
