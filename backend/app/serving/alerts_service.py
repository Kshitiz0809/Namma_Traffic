"""
Phase 6 Task 2 — GET /alerts. Live version of the Phase 5 alerts.json
generation, computed over ALL current cells (not just a validation-period
sample), filterable by level and limited for dashboard consumption.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.serving.risk_snapshot import get_all_cell_risk_snapshot

router = APIRouter()

CONTRIBUTION_COLUMNS = [
    "contribution_hotspot_probability",
    "contribution_normalized_predicted_count",
    "contribution_persistence",
    "contribution_recent_intensity",
]


def _top_factors(row, top_n: int = 2) -> list[dict]:
    contributions = {col.replace("contribution_", ""): row[col] for col in CONTRIBUTION_COLUMNS}
    ranked = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [{"factor": name, "contribution": round(float(value), 2)} for name, value in ranked]


@router.get("/alerts")
def alerts(
    level: str | None = Query(None, description="Filter by alert level: GREEN, YELLOW, ORANGE, RED"),
    min_band: str = Query("MEDIUM", description="Minimum risk band to include (LOW excluded by default)"),
    limit: int = Query(50, ge=1, le=500),
):
    snapshot = get_all_cell_risk_snapshot()

    band_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    min_idx = band_order.index(min_band) if min_band in band_order else 1
    included_bands = set(band_order[min_idx:])

    df = snapshot[snapshot["final_risk_band"].isin(included_bands)]
    if level:
        df = df[df["alert_level"] == level.upper()]

    df = df.nlargest(limit, "risk_score")

    results = [
        {
            "zone": row["h3_cell"],
            "junction_name": row["junction_name"],
            "police_station": row["police_station"],
            "latitude": round(float(row["latitude"]), 6),
            "longitude": round(float(row["longitude"]), 6),
            "alert_level": row["alert_level"],
            "probability": round(float(row["hotspot_probability"]), 4),
            "risk_score": round(float(row["risk_score"]), 2),
            "risk_band": row["final_risk_band"],
            "recommendation": row["recommendation"],
            "escalated": bool(row["escalated"]),
            "top_contributing_factors": _top_factors(row),
            "last_known_event": row["last_known_event"],
            "carriageway_impact_score": round(float(row["carriageway_impact_score"]), 2),
            "carriageway_impact_label": row["carriageway_impact_label"],
            "hotspot_trend": row["hotspot_trend"],
        }
        for _, row in df.iterrows()
    ]

    return {
        "count": len(results),
        "total_cells_evaluated": len(snapshot),
        "alerts": results,
    }
