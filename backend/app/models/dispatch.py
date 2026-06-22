"""
Phase 9 — patrol dispatch optimizer (ADR-026).

Turns the risk snapshot from a list you have to read into a list you can
act on: given N available patrol units and the live risk-score snapshot,
computes which unit should go to which hotspot to maximize distinct
hotspot coverage, instead of leaving "where do I send my 3 available
patrols" as a manual judgment call made by staring at a map.

Unit starting locations are derived from the dataset itself — the
centroid of each `police_station`'s own historical violations — not an
external facilities database, keeping this compliant with the
internal-data-only constraint (ADR-001). Travel time is a straight-line
haversine distance at a disclosed assumed urban average speed — a
deliberately simple proxy, not a claim of real road-network ETAs (no
external routing API is used or permitted).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

EARTH_RADIUS_KM = 6371.0
ASSUMED_PATROL_SPEED_KMPH = 25.0  # disclosed urban-average assumption, not measured/derived
MIN_TARGET_SEPARATION_KM = 0.5  # don't send two units to essentially the same spot


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype=float)) for x in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def get_station_centroids(features: pd.DataFrame) -> pd.DataFrame:
    """One row per `police_station`: centroid lat/lon of its own historical
    violations — a real, data-derived proxy for "where this station's
    patrols are based," since no station-address field exists in the
    provided schema.
    """
    stations = (
        features.dropna(subset=["police_station", "latitude", "longitude"])
        .groupby("police_station")[["latitude", "longitude"]]
        .mean()
        .reset_index()
        .rename(columns={"latitude": "origin_lat", "longitude": "origin_lon"})
    )
    return stations


@dataclass
class DispatchAssignment:
    unit_id: int
    origin_station: str
    origin_lat: float
    origin_lon: float
    target_h3_cell: str
    target_junction: str
    target_lat: float
    target_lon: float
    target_risk_score: float
    target_risk_band: str
    distance_km: float
    eta_minutes: float


def _select_targets(risk_df: pd.DataFrame, n_targets: int) -> pd.DataFrame:
    """Greedily picks up to n_targets highest-risk cells, skipping any
    candidate within MIN_TARGET_SEPARATION_KM of an already-picked one —
    avoids wasting two units on the same cluster when other real hotspots
    are uncovered.
    """
    candidates = risk_df.sort_values("risk_score", ascending=False).reset_index(drop=True)
    picked_rows: list[pd.Series] = []
    picked_lat: list[float] = []
    picked_lon: list[float] = []
    for _, row in candidates.iterrows():
        if len(picked_rows) >= n_targets:
            break
        if picked_lat:
            d = haversine_km(np.array(picked_lat), np.array(picked_lon), row["latitude"], row["longitude"])
            if (d < MIN_TARGET_SEPARATION_KM).any():
                continue
        picked_rows.append(row)
        picked_lat.append(row["latitude"])
        picked_lon.append(row["longitude"])
    if not picked_rows:
        return candidates.iloc[0:0]
    return pd.DataFrame(picked_rows).reset_index(drop=True)


def compute_patrol_plan(risk_df: pd.DataFrame, station_centroids: pd.DataFrame, n_units: int) -> dict:
    empty_summary = {
        "n_units": 0, "total_risk_covered": 0.0, "total_distance_km": 0.0,
        "avg_eta_minutes": 0.0, "naive_single_target_risk_covered": 0.0,
        "distinct_hotspots_covered": 0,
    }
    if n_units <= 0 or station_centroids.empty:
        return {"assignments": [], "summary": empty_summary}

    targets = _select_targets(risk_df, n_units)
    if targets.empty:
        return {"assignments": [], "summary": empty_summary}

    n_targets = len(targets)
    n_rows = max(n_units, n_targets)
    station_rows = [station_centroids.iloc[i % len(station_centroids)] for i in range(n_rows)]

    cost = np.zeros((n_rows, n_targets))
    for i, srow in enumerate(station_rows):
        cost[i, :] = haversine_km(
            srow["origin_lat"], srow["origin_lon"],
            targets["latitude"].to_numpy(), targets["longitude"].to_numpy(),
        )

    row_ind, col_ind = linear_sum_assignment(cost)

    assignments: list[DispatchAssignment] = []
    for unit_id, (r, c) in enumerate(zip(row_ind, col_ind), start=1):
        if unit_id > n_units:
            break
        srow = station_rows[r]
        trow = targets.iloc[c]
        dist = float(cost[r, c])
        assignments.append(DispatchAssignment(
            unit_id=unit_id,
            origin_station=str(srow["police_station"]),
            origin_lat=float(srow["origin_lat"]),
            origin_lon=float(srow["origin_lon"]),
            target_h3_cell=str(trow["h3_cell"]),
            target_junction=str(trow.get("junction_name", "")),
            target_lat=float(trow["latitude"]),
            target_lon=float(trow["longitude"]),
            target_risk_score=float(trow["risk_score"]),
            target_risk_band=str(trow["final_risk_band"]),
            distance_km=round(dist, 2),
            eta_minutes=round(dist / ASSUMED_PATROL_SPEED_KMPH * 60, 1),
        ))

    total_risk_covered = sum(a.target_risk_score for a in assignments)
    total_distance = sum(a.distance_km for a in assignments)
    avg_eta = (total_distance / len(assignments) / ASSUMED_PATROL_SPEED_KMPH * 60) if assignments else 0.0

    # Naive baseline: every available unit converges on the single
    # highest-risk cell — only ONE distinct hotspot actually gets covered
    # no matter how many units you have. This is what the optimizer beats.
    naive_target_risk = float(risk_df["risk_score"].max()) if len(risk_df) else 0.0

    return {
        "assignments": [asdict(a) for a in assignments],
        "summary": {
            "n_units": len(assignments),
            "total_risk_covered": round(total_risk_covered, 2),
            "total_distance_km": round(total_distance, 2),
            "avg_eta_minutes": round(avg_eta, 1),
            "naive_single_target_risk_covered": round(naive_target_risk, 2),
            "distinct_hotspots_covered": len(assignments),
        },
    }
