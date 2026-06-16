"""
Shared "current risk state, all cells" computation — used by both
`alerts_service.py` (GET /alerts) and the dashboard's Live Risk Map. Same
"latest historical snapshot per cell" approximation as `forecast_service.py`
(no live streaming yet — Phase 7), computed once per process and cached.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor

from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from app.models.recommendation import load_rules, recommend
from app.models.risk_score import RiskMinMaxParams, compute_risk_score

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

_snapshot_df: pd.DataFrame | None = None


def get_all_cell_risk_snapshot() -> pd.DataFrame:
    """One row per H3 cell: hotspot_probability, predicted_count, risk_score,
    risk_band, recommendation, alert_level, lat/lon (cell centroid), and the
    top-2 contributing factors. Computed once, cached for the process lifetime.
    """
    global _snapshot_df
    if _snapshot_df is not None:
        return _snapshot_df

    classifier = CatBoostClassifier()
    classifier.load_model(str(MODELS_DIR / "classifier_catboost.cbm"))
    regressor = CatBoostRegressor()
    regressor.load_model(str(MODELS_DIR / "regressor_catboost.cbm"))
    with open(MODELS_DIR / "risk_minmax_params.json", encoding="utf-8") as f:
        risk_params = RiskMinMaxParams(**json.load(f))
    rules = load_rules()

    features = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    latest_idx = features.groupby("h3_cell")["created_datetime"].idxmax()
    latest = features.loc[latest_idx].reset_index(drop=True)

    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    X = latest[feature_cols].copy()
    for col in NUMERIC_FEATURES:
        if X[col].dtype == bool:
            X[col] = X[col].astype(int)
    for col in CATEGORICAL_FEATURES:
        X[col] = X[col].astype("string").fillna("MISSING").astype("category")

    hotspot_proba = classifier.predict_proba(X)[:, 1]
    predicted_count = regressor.predict(X)

    risk_df = compute_risk_score(hotspot_proba, predicted_count, latest, risk_params)
    risk_df["h3_cell"] = latest["h3_cell"].to_numpy()
    risk_df["latitude"] = latest["latitude"].to_numpy()
    risk_df["longitude"] = latest["longitude"].to_numpy()
    risk_df["junction_name"] = latest["junction_name"].to_numpy()
    risk_df["police_station"] = latest["police_station"].to_numpy()
    risk_df["vehicle_type"] = latest["vehicle_type"].to_numpy()
    risk_df["junction_historical_risk"] = latest["junction_historical_risk"].to_numpy()
    risk_df["last_known_event"] = latest["created_datetime"].astype(str).to_numpy()

    recommendations = [
        recommend(
            risk_band=row["risk_band"],
            vehicle_type=row["vehicle_type"],
            junction_name=row["junction_name"],
            junction_historical_risk=float(row["junction_historical_risk"]),
            rules=rules,
        )
        for _, row in risk_df.iterrows()
    ]
    risk_df["final_risk_band"] = [r.risk_band for r in recommendations]
    risk_df["recommendation"] = [r.final_action for r in recommendations]
    risk_df["escalated"] = [r.escalated for r in recommendations]

    alert_color = {"LOW": "GREEN", "MEDIUM": "YELLOW", "HIGH": "ORANGE", "CRITICAL": "RED"}
    risk_df["alert_level"] = risk_df["final_risk_band"].map(alert_color)

    _snapshot_df = risk_df
    return risk_df
