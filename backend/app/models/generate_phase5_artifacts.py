"""
Phase 5 orchestrator: computes risk_score + recommendations for the
validation split (frozen models, no retraining), generates alerts.json,
and prints the risk distribution for review.

Run directly: `python -m app.models.generate_phase5_artifacts`
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor

from app.models.alerts import generate_alerts
from app.models.classifier import build_classification_dataset
from app.models.feature_set import NUMERIC_FEATURES, REDUCED_SPATIAL_CATEGORICAL_FEATURES
from app.models.recommendation import load_rules, recommend
from app.models.risk_score import RiskParams, compute_risk_score

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
DOCS_DIR = PROJECT_ROOT / "docs"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def run() -> dict:
    features = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    targets = pd.read_parquet(PROCESSED_DIR / "targets.parquet")
    split = build_classification_dataset(features, targets)
    feature_cols = NUMERIC_FEATURES + REDUCED_SPATIAL_CATEGORICAL_FEATURES

    clf = CatBoostClassifier()
    clf.load_model(str(MODELS_DIR / "classifier_catboost.cbm"))
    reg = CatBoostRegressor()
    reg.load_model(str(MODELS_DIR / "regressor_catboost.cbm"))

    with open(MODELS_DIR / "risk_params.json", encoding="utf-8") as f:
        risk_params = RiskParams(**json.load(f))

    rules = load_rules()

    X_val = split.val[feature_cols]
    hotspot_proba = clf.predict_proba(X_val)[:, 1]
    predicted_count = reg.predict(X_val)

    risk_df = compute_risk_score(hotspot_proba, predicted_count, split.val, risk_params)

    recommendations = [
        recommend(
            risk_band=row["risk_band"],
            vehicle_type=split.val["vehicle_type"].iloc[i],
            junction_name=split.val["junction_name"].iloc[i],
            junction_historical_risk=float(split.val["junction_historical_risk"].iloc[i]),
            rules=rules,
        )
        for i, (_, row) in enumerate(risk_df.iterrows())
    ]

    # Carry h3_cell/junction_name/created_datetime into risk_df for alert generation.
    risk_df["h3_cell"] = split.val["h3_cell"].to_numpy()
    risk_df["junction_name"] = split.val["junction_name"].to_numpy()
    risk_df["created_datetime"] = split.val["created_datetime"].to_numpy()

    alerts = generate_alerts(risk_df, recommendations, min_band="MEDIUM", max_per_band=20)
    with open(DOCS_DIR / "alerts.json", "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2, default=str)

    recommendation_counts = pd.Series([r.final_action for r in recommendations]).value_counts()
    band_counts = risk_df["risk_band"].value_counts()
    escalation_count = sum(1 for r in recommendations if r.escalated)

    return {
        "risk_score_distribution": risk_df["risk_score"].describe().to_dict(),
        "risk_band_counts": band_counts.to_dict(),
        "recommendation_counts": recommendation_counts.to_dict(),
        "escalations": escalation_count,
        "n_alerts_generated": len(alerts),
        "alerts_by_level": pd.Series([a["alert_level"] for a in alerts]).value_counts().to_dict(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    summary = run()
    print(json.dumps(summary, indent=2, default=str))
