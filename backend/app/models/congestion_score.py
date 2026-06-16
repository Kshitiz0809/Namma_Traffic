"""
Congestion score — a derived, REPORTED metric (ADR-011), not a model
training target. Computed entirely from features already validated in
Phase 2; no new raw-column dependencies.

    congestion_score = 0.5 * normalized_violation_count
                      + 0.3 * hotspot_persistence
                      + 0.2 * enforcement_density

Component definitions (all leakage-safe, all min-max scaled using
statistics fit on the TRAIN split only — see DECISIONS.md ADR-011 for why
fitting on val/test would leak their distribution into a score meant to
generalize):
- normalized_violation_count <- violation_density
- hotspot_persistence        <- rolling_hotspot_intensity
- enforcement_density        <- police_station_density
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

WEIGHTS = {
    "normalized_violation_count": 0.5,
    "hotspot_persistence": 0.3,
    "enforcement_density": 0.2,
}

SOURCE_COLUMNS = {
    "normalized_violation_count": "violation_density",
    "hotspot_persistence": "rolling_hotspot_intensity",
    "enforcement_density": "police_station_density",
}


@dataclass
class MinMaxParams:
    mins: dict[str, float]
    maxs: dict[str, float]


def fit_minmax(train_df: pd.DataFrame) -> MinMaxParams:
    mins, maxs = {}, {}
    for source_col in SOURCE_COLUMNS.values():
        mins[source_col] = float(train_df[source_col].min())
        maxs[source_col] = float(train_df[source_col].max())
    return MinMaxParams(mins=mins, maxs=maxs)


def _scale(series: pd.Series, col: str, params: MinMaxParams) -> pd.Series:
    lo, hi = params.mins[col], params.maxs[col]
    if hi <= lo:
        return pd.Series(0.0, index=series.index)
    scaled = (series - lo) / (hi - lo)
    return scaled.clip(0.0, 1.0)  # val/test rows outside train's observed range get clipped, not extrapolated


def compute_congestion_score(df: pd.DataFrame, params: MinMaxParams) -> pd.DataFrame:
    """Returns a DataFrame with the 3 normalized components + final
    congestion_score, indexed like `df`.
    """
    out = pd.DataFrame(index=df.index)
    for component, source_col in SOURCE_COLUMNS.items():
        out[component] = _scale(df[source_col], source_col, params)

    out["congestion_score"] = sum(
        WEIGHTS[component] * out[component] for component in WEIGHTS
    )
    return out
