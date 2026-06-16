"""
Rolling/windowed features — all leakage-safe per ADR-006: every window is
computed using `closed='left'` (or an explicit per-row shift), meaning the
current row's own occurrence is never counted in its own feature value.

Requires `h3_cell` (spatial.py) and `created_datetime`.
"""

from __future__ import annotations

import pandas as pd

ROLLING_WINDOWS_MINUTES = [15, 30, 60]
HOTSPOT_INTENSITY_HALFLIFE_HOURS = 24


def _rolling_count(sorted_df: pd.DataFrame, minutes: int) -> pd.Series:
    """Count of OTHER rows in the same h3_cell within the preceding `minutes`
    window. `sorted_df` must already be sorted by created_datetime.

    Note: we deliberately keep each group's original row labels (via
    `g.index`) rather than re-indexing by `created_datetime` after the
    groupby — duplicate timestamps within a cell (which exist in this
    dataset) would otherwise silently collide and misalign results back
    onto the wrong rows.
    """
    def _per_group(g: pd.DataFrame) -> pd.Series:
        s = g.set_index("created_datetime")["id"].rolling(f"{minutes}min", closed="left").count()
        s.index = g.index
        return s

    counts = sorted_df.groupby("h3_cell", group_keys=False).apply(_per_group, include_groups=False)
    return counts.reindex(sorted_df.index).fillna(0)


def add_rolling_window_counts(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    original_index = df.index
    sorted_df = df.sort_values("created_datetime", kind="stable")

    for minutes in ROLLING_WINDOWS_MINUTES:
        col = f"violations_last_{minutes}m"
        sorted_df[col] = _rolling_count(sorted_df, minutes)

    return sorted_df.loc[original_index]


def add_same_hour_previous_day(df: pd.DataFrame) -> pd.DataFrame:
    """For each row, count of violations in the same h3_cell at the same
    hour-of-day exactly one calendar day before. Leakage-safe by construction
    (only ever looks at the prior day, never the current or future day).
    """
    df = df.copy()
    if "hour" not in df.columns:
        raise ValueError("add_same_hour_previous_day requires 'hour' column — run temporal features first")

    date = df["created_datetime"].dt.date
    daily_hourly_counts = (
        df.assign(_date=date)
        .groupby(["h3_cell", "_date", "hour"])
        .size()
        .rename("count")
        .reset_index()
    )

    lookup = df.assign(_date=date, _prev_date=date - pd.Timedelta(days=1))[
        ["h3_cell", "_prev_date", "hour"]
    ].rename(columns={"_prev_date": "_date"})

    merged = lookup.merge(
        daily_hourly_counts, on=["h3_cell", "_date", "hour"], how="left"
    )
    df["same_hour_previous_day"] = merged["count"].fillna(0).to_numpy()
    return df


def add_rolling_hotspot_intensity(df: pd.DataFrame) -> pd.DataFrame:
    """Exponentially-weighted occurrence intensity per h3_cell (halflife =
    24h), using pandas' `times=` EWM support for irregularly-spaced
    timestamps, EXCLUDING the current row's own occurrence (leakage-safe).

    Implementation note: `Series.ewm(times=...).mean()` computes a weighted
    *average* of past values, not a decayed *sum* — on a constant indicator
    series of all-1s (one row per event) that average is trivially always
    1.0 regardless of decay, so it carries no signal. What we actually want
    is a Hawkes-process-style decayed sum: each event contributes 1.0 at the
    moment it happens, and that contribution decays with a 24h halflife as
    time passes. That recursion (`intensity = intensity * decay + 1` per new
    event) has no vectorized pandas equivalent, so it's computed with a
    single O(n) pass over time-sorted rows, tracking one running value per
    h3_cell.
    """
    df = df.copy()
    original_index = df.index
    sorted_df = df.sort_values("created_datetime", kind="stable")

    halflife_hours = HOTSPOT_INTENSITY_HALFLIFE_HOURS
    times = sorted_df["created_datetime"].to_numpy()
    cells = sorted_df["h3_cell"].to_numpy()

    last_time: dict[str, "np.datetime64"] = {}
    last_intensity: dict[str, float] = {}
    out = pd.Series(0.0, index=sorted_df.index)

    for pos, (cell, t) in enumerate(zip(cells, times)):
        if cell in last_time:
            elapsed_hours = (t - last_time[cell]) / pd.Timedelta(hours=1).to_timedelta64()
            decayed = last_intensity[cell] * (0.5 ** (elapsed_hours / halflife_hours))
        else:
            decayed = 0.0
        out.iloc[pos] = decayed  # value BEFORE this event is added — excludes self
        last_intensity[cell] = decayed + 1.0
        last_time[cell] = t

    sorted_df = sorted_df.copy()
    sorted_df["rolling_hotspot_intensity"] = out
    return sorted_df.loc[original_index]


def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_rolling_window_counts(df)
    df = add_same_hour_previous_day(df)
    df = add_rolling_hotspot_intensity(df)
    return df
