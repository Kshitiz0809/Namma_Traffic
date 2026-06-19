"""
The model feature set — what a live prediction is actually allowed to see.

This is intentionally a SMALLER set than every column in features.parquet.
features.parquet keeps everything (including descriptive/administrative
columns) per the "flag, don't drop" philosophy; this module is where the
narrower "what's available at prediction time" decision (ADR-009, ADR-013)
actually gets enforced as code, not just as a docstring promise.
"""

from __future__ import annotations

import pandas as pd

# Numeric features available at created_datetime (no post-hoc admin fields).
NUMERIC_FEATURES = [
    "hotspot_frequency",
    "violation_density",
    "junction_density",
    "police_station_density",
    "neighbor_hotspot_frequency",
    "neighbor_violation_density",
    "neighbor_junction_density",
    "neighbor_police_station_density",
    "neighbor_rolling_hotspot_intensity",
    "neighbor_violations_last_15m",
    "hour",
    "weekday",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "is_peak_hour",
    "violation_frequency",
    "violations_last_15m",
    "violations_last_30m",
    "violations_last_60m",
    "same_hour_previous_day",
    "rolling_hotspot_intensity",
    "junction_historical_risk",
    "offence_historical_risk",
    "vehicle_type_historical_risk",
    "center_code_historical_risk",
    "num_offences",
    "is_outlier_coordinate",
    "is_duplicate_vehicle_event",
]

# Categorical features — kept as pandas "category" dtype; each model library
# handles them natively (CatBoost: cat_features=; LightGBM: categorical_feature=;
# XGBoost: enable_categorical=True), no manual one-hot/label encoding needed.
CATEGORICAL_FEATURES = [
    "h3_cell",
    "junction_name",
    "police_station",
    "center_code",
    "vehicle_type",
    "primary_offence_code",
    "primary_violation_type",
]

# GeoHash variant of the spatial key, used only for Experiment C (ADR-012).
# Swapping h3_cell -> geohash means dropping h3_cell-derived density features
# too, since those were computed keyed on h3_cell specifically.
GEOHASH_CATEGORICAL_FEATURES = [
    "geohash" if c == "h3_cell" else c for c in CATEGORICAL_FEATURES
]

# "Raw counts only" variant for Experiment D — drops every rolling/temporal
# windowed feature, keeping just the simplest historical count.
RAW_COUNT_ONLY_NUMERIC_FEATURES = [
    c for c in NUMERIC_FEATURES
    if c not in {
        "violations_last_15m", "violations_last_30m", "violations_last_60m",
        "same_hour_previous_day", "rolling_hotspot_intensity",
    }
]

# Reduced-spatial-identity variant (Phase 3.5/4 final robustness experiment,
# DECISIONS.md ADR-019) — drops the direct spatial-grid identity columns
# (h3_cell, geohash) that the spatial holdout test (ADR-016) and SHAP audit
# (ADR-017) flagged as a memorization risk, while KEEPING every
# density/rolling/temporal/aggregated-historical feature that describes a
# cell's behavior without naming the cell itself. junction_name/police_station/
# center_code are organizational identifiers, not grid-cell IDs, and are
# deliberately NOT removed here — the experiment targets the specific
# h3_cell/geohash dominance finding, not categorical features in general.
REDUCED_SPATIAL_CATEGORICAL_FEATURES = [
    c for c in CATEGORICAL_FEATURES if c not in {"h3_cell", "geohash"}
]

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def prepare_model_frame(
    df: pd.DataFrame,
    numeric_features: list[str] = NUMERIC_FEATURES,
    categorical_features: list[str] = CATEGORICAL_FEATURES,
) -> pd.DataFrame:
    """Select + type-cast the feature columns a model will actually train on.
    Booleans -> int (some libraries reject bool dtype), categoricals -> pandas
    'category' dtype (required by LightGBM/XGBoost native categorical support).
    """
    cols = numeric_features + categorical_features
    out = df[cols].copy()

    for col in numeric_features:
        if out[col].dtype == bool:
            out[col] = out[col].astype(int)

    for col in categorical_features:
        # Fill missing categoricals with an explicit "MISSING" category rather
        # than leaving NaN — CatBoost rejects NaN in cat_features outright,
        # and "value is missing" is itself a potentially useful signal (e.g.
        # center_code is null for 11,255 rows) rather than something to hide.
        out[col] = out[col].astype("string").fillna("MISSING").astype("category")

    return out
