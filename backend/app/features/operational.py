"""
Operational features — derived from the case-lifecycle timestamp columns and
`vehicle_number`. No external data.

IMPORTANT data-quality finding (see docs/data_quality_report.md, Phase 2
audit): in this dataset, `closed_datetime` and `action_taken_timestamp` are
**100% missing** (298,450 / 298,450 rows). That makes `resolution_time` as
originally specified (closed_datetime - created_datetime) uncomputable —
the column is created anyway (all-NaN) for schema/API compatibility, but it
carries no signal in this dataset. `enforcement_delay` is built from
`data_sent_to_scita_timestamp` instead, which is the next-best lifecycle
timestamp available (~14% coverage). `validation_delay` uses
`validation_timestamp` (~58% coverage). All three are genuinely sparse —
this is reported, not hidden, and feature_dictionary.md flags expected
missingness for each.

`violation_frequency` is leakage-safe (ADR-006): expanding count of a
vehicle's prior violations, using only rows strictly before the current one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _minutes_between(later: pd.Series, earlier: pd.Series) -> pd.Series:
    delta = (later - earlier).dt.total_seconds() / 60.0
    return delta


def add_delay_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["resolution_time_minutes"] = _minutes_between(df["closed_datetime"], df["created_datetime"])
    df["enforcement_delay_minutes"] = _minutes_between(
        df["data_sent_to_scita_timestamp"], df["created_datetime"]
    )
    df["validation_delay_minutes"] = _minutes_between(
        df["validation_timestamp"], df["created_datetime"]
    )
    return df


def add_violation_frequency(df: pd.DataFrame) -> pd.DataFrame:
    """Expanding count of prior violations for the same vehicle_number
    (repeat-offender signal). Rows with a missing vehicle_number get NaN —
    "frequency of an unknown vehicle" isn't a meaningful number, and treating
    all unknowns as one giant pseudo-vehicle would be actively misleading.
    """
    df = df.copy()
    original_index = df.index

    has_vehicle = df["vehicle_number"].notna()
    result = pd.Series(np.nan, index=df.index, dtype="float64")

    known = df.loc[has_vehicle].sort_values("created_datetime", kind="stable")
    known_freq = known.groupby("vehicle_number").cumcount().astype("float64")
    result.loc[known.index] = known_freq.values

    df["violation_frequency"] = result.loc[original_index]
    return df


def add_operational_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_delay_features(df)
    df = add_violation_frequency(df)
    return df
