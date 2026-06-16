"""
Temporal features, all derived from `created_datetime` alone.

Calendar reads (`hour`, `weekday`, `is_weekend`, `hour_sin`, `hour_cos`) carry
zero leakage risk — they're just clock arithmetic, not statistics learned
from the data.

`is_peak_hour` is different: "peak" is a relative/statistical notion (which
hours are busiest), so naively computing it from the full dataset and
applying it to every row would let early rows see future popularity
patterns. Per ADR-006, it's computed as an **expanding** ranking — at each
row's timestamp, only hours' cumulative counts from rows strictly before
it are used to decide whether the current hour is in the (so far) busiest
quartile.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PEAK_HOUR_TOP_K = 6  # top quartile of 24 hours


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    dt = df["created_datetime"]
    df["hour"] = dt.dt.hour
    df["weekday"] = dt.dt.dayofweek  # 0=Monday
    df["is_weekend"] = df["weekday"].isin([5, 6])
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    return df


def add_peak_hour_feature(df: pd.DataFrame) -> pd.DataFrame:
    """Requires `hour` (call add_calendar_features first) and `created_datetime`.
    Sorts internally by created_datetime for the expanding computation, then
    restores original row order.
    """
    df = df.copy()
    original_index = df.index
    sorted_df = df.sort_values("created_datetime", kind="stable")

    hours = sorted_df["hour"].to_numpy()
    is_peak = np.zeros(len(sorted_df), dtype=bool)
    counts = np.zeros(24, dtype=np.int64)

    for i, h in enumerate(hours):
        # Rank using counts accumulated from strictly-prior rows only.
        threshold = np.sort(counts)[::-1][PEAK_HOUR_TOP_K - 1]
        is_peak[i] = counts[h] >= threshold and counts[h] > 0
        counts[h] += 1

    sorted_df["is_peak_hour"] = is_peak
    return sorted_df.loc[original_index]


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_calendar_features(df)
    df = add_peak_hour_feature(df)
    return df
