"""
Phase 5 Task 4 — Forecast Service: `GET /forecast`.

IMPORTANT, HONEST LIMITATION (see docs/risk_definition.md and README Phase 5
section): there is no live streaming pipeline yet (that's Phase 7). This
endpoint looks up the most recent HISTORICAL snapshot of a given H3 cell's
engineered features (from `data/processed/features.parquet`) as a proxy for
"current state" — `hour`/`weekday`/cyclic-time features are recomputed
against the REAL current timestamp at request time (those should reflect
"now", not the last historical event), but density/rolling/historical-risk
features are frozen at whatever they were the last time that cell had a
recorded violation. This is a documented approximation, not a claim of
real-time accuracy.

Cold start: if a requested H3 cell has no historical rows at all, this
returns a degraded response (conservative LOW risk, zero confidence,
`is_cold_start: true`) rather than fabricating a number — consistent with
the spatial-holdout limitation (DECISIONS.md ADR-016): the model is not
validated to generalize confidently to genuinely unseen cells.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from fastapi import APIRouter, HTTPException, Query

from app.models.carriageway_impact import compute_carriageway_impact
from app.models.feature_set import NUMERIC_FEATURES, REDUCED_SPATIAL_CATEGORICAL_FEATURES
from app.models.hotspot_trend import classify_hotspot_trend
from app.models.recommendation import load_rules, recommend
from app.models.risk_score import RiskParams, compute_risk_score

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
H3_RESOLUTION = 9  # must match backend/app/features/spatial.py

router = APIRouter()

_classifier: CatBoostClassifier | None = None
_regressor: CatBoostRegressor | None = None
_risk_params: RiskParams | None = None
_recommendation_rules: dict | None = None
_latest_by_cell: pd.DataFrame | None = None


def reload_state() -> None:
    """Clear cached module state so the next request lazy-reloads fresh
    models/parquet/params from disk — called by the admin retrain endpoint
    after `retrain.run_pipeline()` writes new artifacts, so a running
    process picks up a retrained model without needing a restart.
    """
    global _classifier, _regressor, _risk_params, _recommendation_rules, _latest_by_cell
    _classifier = _regressor = _risk_params = _recommendation_rules = _latest_by_cell = None


def _load_state() -> None:
    """Lazy-loaded module state — avoids re-reading parquet/models on every
    request, and avoids loading them at import time for modules that only
    need other parts of `app.serving`.
    """
    global _classifier, _regressor, _risk_params, _recommendation_rules, _latest_by_cell
    if _classifier is not None:
        return

    _classifier = CatBoostClassifier()
    _classifier.load_model(str(MODELS_DIR / "classifier_catboost.cbm"))

    _regressor = CatBoostRegressor()
    _regressor.load_model(str(MODELS_DIR / "regressor_catboost.cbm"))

    with open(MODELS_DIR / "risk_params.json", encoding="utf-8") as f:
        _risk_params = RiskParams(**json.load(f))

    _recommendation_rules = load_rules()

    # idxmax-based "latest row per cell" rather than a full sort_values() +
    # groupby().tail(1) — lighter on memory for a 298k-row, many-column
    # table (a full sort hit an allocation failure in some constrained
    # execution contexts; idxmax only needs one pass over created_datetime).
    features = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    # Computed over full per-cell history before reducing to "latest row per
    # cell" -- see risk_snapshot.py for the same ordering and why.
    features = compute_carriageway_impact(features, _recommendation_rules)
    latest_idx = features.groupby("h3_cell")["created_datetime"].idxmax()
    _latest_by_cell = features.loc[latest_idx].set_index("h3_cell")


def _resolve_h3_cell(h3_cell: str | None, lat: float | None, lon: float | None) -> str:
    if h3_cell:
        return h3_cell
    if lat is not None and lon is not None:
        return h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
    raise HTTPException(status_code=400, detail="Provide either h3_cell or both lat and lon.")


def _build_feature_row(snapshot: pd.Series, vehicle_type_override: str | None) -> pd.DataFrame:
    """Numeric/historical-risk features come from the last known snapshot
    (see module docstring); hour/weekday/cyclic-time are recomputed against
    the real current time. vehicle_type can be overridden by the caller
    (the vehicle actually being evaluated right now), defaulting to the
    snapshot's last-known vehicle_type if not provided.
    """
    now = datetime.now(timezone.utc)
    row = snapshot.copy()
    row["hour"] = now.hour
    row["weekday"] = now.weekday()
    row["is_weekend"] = int(now.weekday() in (5, 6))
    row["hour_sin"] = np.sin(2 * np.pi * now.hour / 24)
    row["hour_cos"] = np.cos(2 * np.pi * now.hour / 24)
    # is_peak_hour is left at the snapshot's last value — recomputing the
    # full expanding-window ranking live would require a full dataset scan;
    # documented approximation, not a live signal (see docstring above).

    if vehicle_type_override:
        row["vehicle_type"] = vehicle_type_override

    for col in NUMERIC_FEATURES:
        if isinstance(row[col], (bool, np.bool_)):
            row[col] = int(row[col])

    return pd.DataFrame([row[NUMERIC_FEATURES + REDUCED_SPATIAL_CATEGORICAL_FEATURES]])


def _cold_start_response(cell: str) -> dict:
    return {
        "zone": cell,
        "hotspot_probability": None,
        "predicted_count": None,
        "congestion_risk": 0.0,
        "risk_band": "LOW",
        "recommendation": "Monitor",
        "confidence": 0.0,
        "top_contributing_factors": [],
        "is_cold_start": True,
        "carriageway_impact_score": 0.0,
        "carriageway_impact_label": "Minimal",
        "hotspot_trend": "STABLE",
        "note": (
            "No historical data for this H3 cell — model is not validated to "
            "generalize confidently to unseen cells (see DECISIONS.md ADR-016). "
            "Returning a conservative default, not a fabricated prediction."
        ),
    }


@router.get("/forecast")
def forecast(
    h3_cell: str | None = Query(None, description="H3 cell ID (resolution 9). Provide this OR lat+lon."),
    lat: float | None = Query(None, description="Latitude, used with lon if h3_cell is not provided."),
    lon: float | None = Query(None, description="Longitude, used with lat if h3_cell is not provided."),
    vehicle_type: str | None = Query(None, description="Override the vehicle type being evaluated right now."),
):
    _load_state()
    cell = _resolve_h3_cell(h3_cell, lat, lon)

    if cell not in _latest_by_cell.index:
        return _cold_start_response(cell)

    snapshot = _latest_by_cell.loc[cell].copy()
    snapshot["h3_cell"] = cell  # restore — dropped from columns by set_index() in _load_state
    feature_row = _build_feature_row(snapshot, vehicle_type)

    hotspot_proba = float(_classifier.predict_proba(feature_row)[:, 1][0])
    predicted_count = float(_regressor.predict(feature_row)[0])

    risk_df = compute_risk_score(
        np.array([hotspot_proba]), np.array([predicted_count]), feature_row, _risk_params
    )
    risk_row = risk_df.iloc[0]

    rec = recommend(
        risk_band=risk_row["risk_band"],
        vehicle_type=feature_row["vehicle_type"].iloc[0],
        junction_name=snapshot["junction_name"],
        junction_historical_risk=float(snapshot["junction_historical_risk"]),
        rules=_recommendation_rules,
    )

    top_factors = sorted(
        [
            {"factor": "hotspot_probability", "contribution": round(float(risk_row["contribution_hotspot_probability"]), 2)},
            {"factor": "normalized_predicted_count", "contribution": round(float(risk_row["contribution_normalized_predicted_count"]), 2)},
            {"factor": "persistence", "contribution": round(float(risk_row["contribution_persistence"]), 2)},
            {"factor": "recent_intensity", "contribution": round(float(risk_row["contribution_recent_intensity"]), 2)},
        ],
        key=lambda x: x["contribution"],
        reverse=True,
    )[:2]

    # Confidence heuristic — NOT a calibrated interval (Phase 3.5 found only
    # moderate calibration, Brier 0.1766, no calibration layer applied).
    # Distance from 0.5 measures how decisively the model leans either way.
    confidence = round(abs(hotspot_proba - 0.5) * 2, 4)

    return {
        "zone": cell,
        "hotspot_probability": round(hotspot_proba, 4),
        "predicted_count": round(predicted_count, 2),
        "congestion_risk": round(float(risk_row["risk_score"]), 2),
        "risk_band": rec.risk_band,
        "recommendation": rec.final_action,
        "confidence": confidence,
        "top_contributing_factors": top_factors,
        "is_cold_start": False,
        "last_known_event": str(snapshot["created_datetime"]),
        "escalated": rec.escalated,
        "carriageway_impact_score": round(float(snapshot["carriageway_impact_score"]), 2),
        "carriageway_impact_label": snapshot["carriageway_impact_label"],
        "hotspot_trend": classify_hotspot_trend(
            pd.Series([snapshot["violations_last_60m"]]),
            pd.Series([snapshot["violation_density"]]),
            pd.Series([rec.risk_band]),
        ).iloc[0],
    }
