"""
Phase 6 Task 2 tests: /alerts, /metrics, OpenAPI docs. Real-data smoke
tests via FastAPI TestClient — frozen models, no retraining.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.slow
def test_alerts_endpoint_returns_sorted_by_risk_descending():
    r = client.get("/alerts", params={"limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] <= 10
    assert body["total_cells_evaluated"] > 0
    scores = [a["risk_score"] for a in body["alerts"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.slow
def test_alerts_endpoint_filters_by_level():
    r = client.get("/alerts", params={"level": "ORANGE", "limit": 50})
    assert r.status_code == 200
    for alert in r.json()["alerts"]:
        assert alert["alert_level"] == "ORANGE"


@pytest.mark.slow
def test_alerts_endpoint_respects_min_band():
    r = client.get("/alerts", params={"min_band": "HIGH", "limit": 50})
    assert r.status_code == 200
    for alert in r.json()["alerts"]:
        assert alert["risk_band"] in {"HIGH", "CRITICAL"}


@pytest.mark.slow
def test_alerts_endpoint_includes_hotspot_trend():
    r = client.get("/alerts", params={"limit": 10})
    assert r.status_code == 200
    for alert in r.json()["alerts"]:
        assert alert["hotspot_trend"] in {"EMERGING", "STEADY", "STABLE"}


@pytest.mark.slow
def test_dispatch_plan_covers_distinct_hotspots():
    r = client.get("/dispatch/plan", params={"n_units": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["n_units_requested"] == 3
    assert len(body["assignments"]) <= 3
    targets = {a["target_h3_cell"] for a in body["assignments"]}
    assert len(targets) == len(body["assignments"])  # no duplicate targets
    for a in body["assignments"]:
        assert a["distance_km"] >= 0
        assert a["eta_minutes"] >= 0


@pytest.mark.slow
def test_dispatch_plan_invalid_n_units_rejected():
    r = client.get("/dispatch/plan", params={"n_units": 0})
    assert r.status_code == 422


@pytest.mark.slow
def test_metrics_endpoint_returns_real_model_numbers():
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["model"]["winner"] == "catboost"
    assert body["operating_threshold"] == 0.15
    assert body["feature_set"].startswith("Self-retraining")
    assert body["live_risk_distribution"]["total_cells"] > 0
    if body["lead_time"] is not None:
        assert body["lead_time"]["n_episodes"] >= 0
        assert 0 <= body["lead_time"]["pct_caught_30m_plus"] <= 100


def test_openapi_schema_lists_all_endpoints():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = set(r.json()["paths"].keys())
    assert {"/forecast", "/alerts", "/metrics", "/health"}.issubset(paths)


def test_docs_ui_loads():
    r = client.get("/docs")
    assert r.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
