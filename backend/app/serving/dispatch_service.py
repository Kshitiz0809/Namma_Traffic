"""
Phase 9 — GET /dispatch/plan. Turns the live risk snapshot into an actual
patrol assignment: given N available units, computes which unit should go
to which hotspot to maximize distinct-hotspot coverage (app/models/dispatch.py),
instead of leaving "where do I send my patrols" as a manual judgment call.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Query

from app.models.dispatch import compute_patrol_plan, get_station_centroids
from app.serving.risk_snapshot import get_all_cell_risk_snapshot

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

_station_centroids: pd.DataFrame | None = None


def reload_state() -> None:
    """Clear the cached station centroids — called after an admin-triggered
    retrain, in case newly-merged data shifts a station's historical centroid.
    """
    global _station_centroids
    _station_centroids = None


def _get_station_centroids() -> pd.DataFrame:
    global _station_centroids
    if _station_centroids is None:
        features = pd.read_parquet(PROCESSED_DIR / "features.parquet", columns=["police_station", "latitude", "longitude"])
        _station_centroids = get_station_centroids(features)
    return _station_centroids


@router.get("/dispatch/plan")
def dispatch_plan(
    n_units: int = Query(5, ge=1, le=50, description="Number of patrol units currently available to dispatch"),
    min_band: str = Query("MEDIUM", description="Minimum risk band a cell must be in to be considered a dispatch target"),
):
    snapshot = get_all_cell_risk_snapshot()
    band_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    min_idx = band_order.index(min_band) if min_band in band_order else 1
    included_bands = set(band_order[min_idx:])
    candidates = snapshot[snapshot["final_risk_band"].isin(included_bands)]

    plan = compute_patrol_plan(candidates, _get_station_centroids(), n_units)
    return {
        "n_units_requested": n_units,
        "n_candidate_hotspots": len(candidates),
        **plan,
    }
