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
def test_metrics_endpoint_returns_real_model_numbers():
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["model"]["winner"] == "catboost"
    assert body["operating_threshold"] == 0.15
    assert body["feature_set"].startswith("Self-retraining")
    assert body["live_risk_distribution"]["total_cells"] > 0


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
