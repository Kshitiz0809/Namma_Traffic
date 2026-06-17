"""
Phase 7 addition — Carriageway-Impact proxy.

Directly targets the hackathon problem statement's "quantify their impact on
traffic flow" requirement, which neither `congestion_score.py` (Phase 3,
generic violation-density/persistence/enforcement blend) nor `risk_score.py`
(Phase 5, model-prediction blend) actually measure. None of the three is
real traffic-flow telemetry — the provided dataset has no speed, volume, or
queue-length columns at all. This module is the most direct dataset-only
proxy available: it estimates how much carriageway WIDTH is being
simultaneously consumed by illegally parked vehicles, not just how many
violations occurred.

    carriageway_impact_score = sum of obstruction_weight(vehicle_type)
        for every violation in the same h3_cell whose event falls within
        the trailing CONCURRENT_WINDOW_MINUTES of this row (this row
        included) -- i.e. "how many car-widths of carriageway are
        estimated to be simultaneously blocked right now."

Obstruction weights reuse the existing high/low-obstruction vehicle
classification already defined in docs/recommendation_rules.yaml (no new
external vehicle-size database — internal-data-only, ADR-001 honored): a
multi-axle/commercial vehicle (LORRY, BUS, TEMPO, ...) is assumed to occupy
roughly 2x the effective carriageway width of a low-obstruction vehicle
(CAR, SCOOTER, ...) when illegally parked. This weight is a STATED
ASSUMPTION, like the false-negative cost ratio in threshold_optimization.py
— not a measured vehicle-footprint table. Replace OBSTRUCTION_WEIGHT_HIGH
with a real value if one becomes available.

This is a SERVING-time/reporting metric, not a new ML training feature —
the frozen Phase 4 feature set is untouched, no retraining occurs.
"""

from __future__ import annotations

import pandas as pd

from app.models.recommendation import load_rules

CONCURRENT_WINDOW_MINUTES = 15
OBSTRUCTION_WEIGHT_HIGH = 2.0
OBSTRUCTION_WEIGHT_LOW = 1.0

IMPACT_LABEL_BINS = [-0.01, 2.0, 5.0, 10.0, float("inf")]
IMPACT_LABELS = ["Minimal", "Moderate", "Significant", "Severe"]


def _obstruction_weights(rules: dict) -> dict[str, float]:
    high = set(rules["vehicle_mix"]["high_obstruction_types"])
    low = set(rules["vehicle_mix"]["low_obstruction_types"])
    weights = {v: OBSTRUCTION_WEIGHT_HIGH for v in high}
    weights.update({v: OBSTRUCTION_WEIGHT_LOW for v in low})
    return weights


def compute_carriageway_impact(features: pd.DataFrame, rules: dict | None = None) -> pd.DataFrame:
    """Adds `carriageway_impact_score` and `carriageway_impact_label` columns.

    Requires `h3_cell`, `created_datetime`, `vehicle_type`. Returns a copy of
    `features` indexed identically to the input.

    Implementation note: mirrors the duplicate-timestamp-safe pattern in
    features/rolling.py (reattach by original row label via `g.index`, not by
    re-indexing on `created_datetime`) — this dataset has rows sharing exact
    timestamps within the same cell, which previously caused a real
    misalignment bug when results were reattached positionally/by datetime.
    """
    if rules is None:
        rules = load_rules()
    weights = _obstruction_weights(rules)

    df = features.copy()
    df["_obstruction_weight"] = df["vehicle_type"].map(weights).fillna(OBSTRUCTION_WEIGHT_LOW)

    original_index = df.index
    sorted_df = df.sort_values("created_datetime", kind="stable")

    parts = []
    for _, g in sorted_df.groupby("h3_cell", sort=False):
        s = g.set_index("created_datetime")["_obstruction_weight"].rolling(
            f"{CONCURRENT_WINDOW_MINUTES}min", closed="both"
        ).sum()
        s.index = g.index
        parts.append(s)
    impact = pd.concat(parts) if parts else pd.Series(dtype=float)
    sorted_df["carriageway_impact_score"] = impact.reindex(sorted_df.index).fillna(0.0).round(2)
    sorted_df["carriageway_impact_label"] = pd.cut(
        sorted_df["carriageway_impact_score"],
        bins=IMPACT_LABEL_BINS,
        labels=IMPACT_LABELS,
    ).astype(str)

    sorted_df = sorted_df.drop(columns=["_obstruction_weight"])
    return sorted_df.loc[original_index]
