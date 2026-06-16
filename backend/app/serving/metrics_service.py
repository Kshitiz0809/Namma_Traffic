"""
Phase 6 Task 2 — GET /metrics. Serves the real, already-computed Phase 3/3.5
model metrics (from docs/leaderboard.csv — never recomputed/retrained here)
plus a live risk-band distribution snapshot for the dashboard's Analytics View.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter

from app.serving.risk_snapshot import get_all_cell_risk_snapshot

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = PROJECT_ROOT / "docs"


@router.get("/metrics")
def metrics():
    leaderboard = pd.read_csv(DOCS_DIR / "leaderboard.csv")

    primary_classifier = leaderboard[
        (leaderboard["objective"] == "hotspot_classification") & (leaderboard["split"] == "test")
    ]
    val_rows = leaderboard[
        (leaderboard["objective"] == "hotspot_classification") & (leaderboard["split"] == "val")
    ]

    snapshot = get_all_cell_risk_snapshot()
    band_counts = snapshot["final_risk_band"].value_counts().to_dict()
    total = len(snapshot)

    spatial_dependency = leaderboard[leaderboard["objective"].str.startswith("spatial_dependency", na=False)]

    return {
        "model": {
            "winner": "catboost",
            "test_metrics": primary_classifier[
                ["model", "pr_auc", "precision", "recall", "f1", "brier_score"]
            ].to_dict(orient="records"),
            "val_comparison": val_rows[["model", "pr_auc", "precision", "recall", "f1"]].to_dict(orient="records"),
        },
        "operating_threshold": 0.15,
        "operational_horizon_minutes": 60,
        "spatial_robustness": {
            "holdout_verdict": "FAIL",
            "holdout_pr_auc_drop_pct": 7.88,
            "abstraction_verdict": "PASS",
            "abstraction_pr_auc_drop_pct": float(
                spatial_dependency[spatial_dependency["objective"].str.contains("model_a")]["pr_auc"].iloc[0]
                - spatial_dependency[spatial_dependency["objective"].str.contains("model_b")]["pr_auc"].iloc[0]
            ) if len(spatial_dependency) == 2 else None,
        },
        "live_risk_distribution": {
            "total_cells": total,
            "band_counts": band_counts,
            "band_pct": {k: round(v / total * 100, 1) for k, v in band_counts.items()},
        },
        "feature_set": "FROZEN (Phase 4 lock, ADR-019)",
        "data_sources": "internal-only (ADR-001) — no external enrichment",
    }
