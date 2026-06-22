"""Phase 9 tests: dispatch.py — synthetic geography with known answers."""

import pandas as pd

from app.models.dispatch import compute_patrol_plan, get_station_centroids, haversine_km


def test_haversine_known_distance_bangalore_to_chennai():
    # Bengaluru (12.9716, 77.5946) -> Chennai (13.0827, 80.2707) is ~290km.
    d = haversine_km(12.9716, 77.5946, 13.0827, 80.2707)
    assert 280 < float(d) < 300


def test_haversine_zero_distance_same_point():
    d = haversine_km(12.97, 77.59, 12.97, 77.59)
    assert float(d) == 0.0


def test_get_station_centroids_averages_per_station():
    features = pd.DataFrame({
        "police_station": ["A", "A", "B"],
        "latitude": [10.0, 12.0, 20.0],
        "longitude": [70.0, 72.0, 80.0],
    })
    out = get_station_centroids(features).set_index("police_station")
    assert out.loc["A", "origin_lat"] == 11.0
    assert out.loc["A", "origin_lon"] == 71.0
    assert out.loc["B", "origin_lat"] == 20.0


def _risk_df(rows):
    df = pd.DataFrame(rows)
    return df


def test_compute_patrol_plan_assigns_distinct_units_to_distinct_hotspots():
    risk_df = _risk_df([
        {"h3_cell": "c1", "junction_name": "J1", "latitude": 12.0, "longitude": 77.0, "risk_score": 90.0, "final_risk_band": "CRITICAL"},
        {"h3_cell": "c2", "junction_name": "J2", "latitude": 12.5, "longitude": 77.5, "risk_score": 70.0, "final_risk_band": "HIGH"},
        {"h3_cell": "c3", "junction_name": "J3", "latitude": 13.0, "longitude": 78.0, "risk_score": 50.0, "final_risk_band": "MEDIUM"},
    ])
    stations = pd.DataFrame({
        "police_station": ["S1", "S2"],
        "origin_lat": [12.0, 13.0],
        "origin_lon": [77.0, 78.0],
    })
    plan = compute_patrol_plan(risk_df, stations, n_units=2)
    assert plan["summary"]["n_units"] == 2
    assert plan["summary"]["distinct_hotspots_covered"] == 2
    targets = {a["target_h3_cell"] for a in plan["assignments"]}
    assert len(targets) == 2  # two DIFFERENT cells covered, not the same one twice


def test_compute_patrol_plan_zero_units_returns_empty():
    risk_df = _risk_df([{"h3_cell": "c1", "junction_name": "J1", "latitude": 12.0, "longitude": 77.0, "risk_score": 90.0, "final_risk_band": "CRITICAL"}])
    stations = pd.DataFrame({"police_station": ["S1"], "origin_lat": [12.0], "origin_lon": [77.0]})
    plan = compute_patrol_plan(risk_df, stations, n_units=0)
    assert plan["assignments"] == []
    assert plan["summary"]["n_units"] == 0


def test_compute_patrol_plan_more_units_than_targets_caps_at_targets():
    risk_df = _risk_df([{"h3_cell": "c1", "junction_name": "J1", "latitude": 12.0, "longitude": 77.0, "risk_score": 90.0, "final_risk_band": "CRITICAL"}])
    stations = pd.DataFrame({"police_station": ["S1", "S2"], "origin_lat": [12.0, 13.0], "origin_lon": [77.0, 78.0]})
    plan = compute_patrol_plan(risk_df, stations, n_units=5)
    assert plan["summary"]["distinct_hotspots_covered"] == 1


def test_naive_baseline_only_covers_one_hotspot_regardless_of_units():
    risk_df = _risk_df([
        {"h3_cell": "c1", "junction_name": "J1", "latitude": 12.0, "longitude": 77.0, "risk_score": 90.0, "final_risk_band": "CRITICAL"},
        {"h3_cell": "c2", "junction_name": "J2", "latitude": 14.0, "longitude": 79.0, "risk_score": 60.0, "final_risk_band": "HIGH"},
    ])
    stations = pd.DataFrame({"police_station": ["S1", "S2"], "origin_lat": [12.0, 14.0], "origin_lon": [77.0, 79.0]})
    plan = compute_patrol_plan(risk_df, stations, n_units=2)
    assert plan["summary"]["naive_single_target_risk_covered"] == 90.0
    assert plan["summary"]["total_risk_covered"] == 150.0  # optimized covers BOTH hotspots
