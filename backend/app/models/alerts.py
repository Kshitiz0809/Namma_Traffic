"""
Phase 5 Task 3 — Alert Layer. Maps risk bands to alert colors (GREEN/
YELLOW/ORANGE/RED), one alert per qualifying row, each with zone,
probability, risk, and top contributing factors (read off the weighted
component contributions already computed in risk_score.py — cheaper and
more directly tied to THIS score than recomputing SHAP per alert).

LOW/GREEN rows don't generate an alert object (nothing actionable to alert
on — "Monitor" is the default state, not an alert).
"""

from __future__ import annotations

import pandas as pd

ALERT_COLOR_BY_BAND = {
    "LOW": "GREEN",
    "MEDIUM": "YELLOW",
    "HIGH": "ORANGE",
    "CRITICAL": "RED",
}

CONTRIBUTION_COLUMNS = [
    "contribution_hotspot_probability",
    "contribution_normalized_predicted_count",
    "contribution_persistence",
    "contribution_recent_intensity",
]


def _top_contributing_factors(row: pd.Series, top_n: int = 2) -> list[dict]:
    contributions = {col.replace("contribution_", ""): row[col] for col in CONTRIBUTION_COLUMNS}
    ranked = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [{"factor": name, "contribution": round(value, 2)} for name, value in ranked]


def build_alert(row: pd.Series, recommendation_action: str, final_band: str) -> dict:
    return {
        "zone": row["h3_cell"],
        "junction_name": row["junction_name"],
        "timestamp": str(row["created_datetime"]),
        "alert_level": ALERT_COLOR_BY_BAND[final_band],
        "probability": round(float(row["hotspot_probability"]), 4),
        "risk_score": round(float(row["risk_score"]), 2),
        "risk_band": final_band,
        "recommendation": recommendation_action,
        "top_contributing_factors": _top_contributing_factors(row),
    }


def generate_alerts(
    risk_df: pd.DataFrame,
    recommendations: list,
    min_band: str = "MEDIUM",
    max_per_band: int = 20,
) -> list[dict]:
    """`risk_df` must have one row per recommendation in `recommendations`
    (same order/index). Returns the highest-risk-score alerts per band, up
    to `max_per_band` each — a representative sample for dashboard/demo
    purposes, not an exhaustive historical alert log (Task 5 notes the
    simulator is "PPT demo only"; this follows the same spirit).
    """
    bands_to_alert = ["MEDIUM", "HIGH", "CRITICAL"]
    start_idx = bands_to_alert.index(min_band) if min_band in bands_to_alert else 0
    bands_to_alert = bands_to_alert[start_idx:]

    df = risk_df.copy()
    df["final_band"] = [r.risk_band for r in recommendations]
    df["recommendation_action"] = [r.final_action for r in recommendations]

    alerts = []
    for band in bands_to_alert:
        band_rows = df[df["final_band"] == band].nlargest(max_per_band, "risk_score")
        for _, row in band_rows.iterrows():
            alerts.append(build_alert(row, row["recommendation_action"], band))

    return alerts
