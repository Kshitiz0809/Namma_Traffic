"""
Phase 7 addition — GET /replay/{scenario}: serves a real historical event
sequence (not synthetic) as ordered JSON points, for the dashboard's replay
mode (Live Risk Map "Replay" button). This is the serving-layer twin of
`app/models/demo_seed.py`'s CLI scenarios — same real cell/date, same frozen
models, JSON out instead of print() to a terminal, so the frontend can
animate it instead of requiring someone to read a terminal during a demo.

Honest framing, disclosed in the response body itself (`is_real_data`,
`label`): this is a REPLAY of a real past sequence, not a live feed. There is
no live streaming pipeline yet (Phase 7 scope — see docs/deployment.md). The
dashboard must label this as "real replay of <date>," never implying it is
happening right now.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.carriageway_impact import compute_carriageway_impact
from app.models.demo_seed import HOTSPOT_GROWTH_CELL, HOTSPOT_GROWTH_DATE, DemoContext

router = APIRouter()

_ctx: DemoContext | None = None

SCENARIOS = {"growth"}


def _get_context() -> DemoContext:
    global _ctx
    if _ctx is None:
        _ctx = DemoContext()
        _ctx.features = compute_carriageway_impact(_ctx.features, _ctx.rules)
    return _ctx


def _growth_points(ctx: DemoContext) -> list[dict]:
    sub = ctx.features[ctx.features["h3_cell"] == HOTSPOT_GROWTH_CELL].copy()
    sub = sub[sub["created_datetime"].dt.date.astype(str) == HOTSPOT_GROWTH_DATE]
    sub = sub.sort_values("created_datetime")

    points = []
    for _, row in sub.iterrows():
        result = ctx.predict_row(row)
        points.append({
            "timestamp": row["created_datetime"].isoformat(),
            "latitude": round(float(row["latitude"]), 6),
            "longitude": round(float(row["longitude"]), 6),
            "junction_name": row["junction_name"],
            "vehicle_type": row["vehicle_type"],
            "violations_last_15m": float(row["violations_last_15m"]),
            "rolling_hotspot_intensity": round(float(row["rolling_hotspot_intensity"]), 2),
            "carriageway_impact_score": round(float(row["carriageway_impact_score"]), 2),
            "carriageway_impact_label": row["carriageway_impact_label"],
            "hotspot_probability": result["hotspot_probability"],
            "predicted_count": result["predicted_count"],
            "risk_score": result["risk_score"],
            "risk_band": result["risk_band"],
            "recommendation": result["recommendation"],
            "escalated": result["escalated"],
        })
    return points


@router.get("/replay/{scenario}")
def replay(scenario: str):
    if scenario not in SCENARIOS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{scenario}'. Available: {sorted(SCENARIOS)}",
        )

    ctx = _get_context()
    points = _growth_points(ctx)

    return {
        "scenario": scenario,
        "label": f"Real replay — {HOTSPOT_GROWTH_DATE} (Elite Junction surge)",
        "cell": HOTSPOT_GROWTH_CELL,
        "is_real_data": True,
        "point_count": len(points),
        "points": points,
    }
