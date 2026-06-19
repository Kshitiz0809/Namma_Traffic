"""
Admin retraining API tests — raw_store dedupe/validation logic, and the
admin_service auth guard + job lifecycle contract. The heavy pipeline steps
(build_features/train/retrain) are NOT exercised here, only mocked at the
boundary — those are covered by actually running `python -m app.models.retrain`
end-to-end (see RELEASE_NOTES.md). These tests cover the fast, deterministic
parts: schema validation, dedupe, and the HTTP contract.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.ingestion import raw_store
from app.ingestion.schema import EXPECTED_COLUMNS
from app.main import app

client = TestClient(app)


def _sample_df(ids: list[str], lat: float = 12.97, lon: float = 77.59) -> pd.DataFrame:
    n = len(ids)
    data = {col: [None] * n for col in EXPECTED_COLUMNS}
    data["id"] = ids
    data["latitude"] = [lat] * n
    data["longitude"] = [lon] * n
    data["created_datetime"] = pd.to_datetime(["2024-01-01T00:00:00Z"] * n)
    return pd.DataFrame(data)


def test_append_new_violations_dedupes_by_id(monkeypatch):
    monkeypatch.setattr(raw_store, "load_master", lambda: _sample_df(["1", "2"]))
    monkeypatch.setattr(pd.DataFrame, "to_csv", lambda *a, **k: None)

    incoming = _sample_df(["2", "3"])  # "2" already exists, "3" is new
    result = raw_store.append_new_violations(incoming)

    assert result.rows_received == 2
    assert result.rows_added == 1
    assert result.rows_duplicate == 1
    assert result.rows_invalid == 0
    assert result.master_row_count == 3


def test_append_new_violations_rejects_rows_missing_required_fields(monkeypatch):
    monkeypatch.setattr(raw_store, "load_master", lambda: _sample_df(["1"]))
    monkeypatch.setattr(pd.DataFrame, "to_csv", lambda *a, **k: None)

    incoming = _sample_df(["2"])
    incoming.loc[0, "latitude"] = None  # REQUIRED_NON_NULL field missing

    result = raw_store.append_new_violations(incoming)
    assert result.rows_added == 0
    assert result.rows_invalid == 1


def test_append_new_violations_rejects_batch_missing_schema_columns(monkeypatch):
    monkeypatch.setattr(raw_store, "load_master", lambda: _sample_df(["1"]))

    incoming = pd.DataFrame({"id": ["2"]})  # missing EXPECTED_COLUMNS entirely
    result = raw_store.append_new_violations(incoming)

    assert result.rows_added == 0
    assert result.rows_invalid == result.rows_received
    assert "missing required columns" in result.invalid_reasons[0]


def test_admin_retrain_rejects_without_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret123")
    r = client.post("/admin/retrain")
    assert r.status_code == 401


def test_admin_retrain_disabled_when_no_token_configured(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "")
    r = client.post("/admin/retrain", headers={"X-Admin-Token": "anything"})
    assert r.status_code == 503


def test_admin_retrain_job_lifecycle_with_valid_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret123")
    monkeypatch.setattr("app.serving.admin_service.load_master", lambda: _sample_df(["1"]))
    monkeypatch.setattr(
        "app.serving.admin_service.retrain.run_pipeline",
        lambda raw_csv_path=None: {"elapsed_seconds": 0.01, "spatial_holdout": {}, "risk_params": {}},
    )

    r = client.post("/admin/retrain", headers={"X-Admin-Token": "secret123"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert r.json()["status"] == "PENDING"

    status_r = client.get(f"/admin/retrain/{job_id}", headers={"X-Admin-Token": "secret123"})
    assert status_r.status_code == 200
    assert status_r.json()["status"] in {"PENDING", "RUNNING", "SUCCESS"}


def test_admin_retrain_status_unknown_job_returns_404(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret123")
    r = client.get("/admin/retrain/not-a-real-job-id", headers={"X-Admin-Token": "secret123"})
    assert r.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
