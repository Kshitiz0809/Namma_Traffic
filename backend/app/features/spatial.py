"""
Spatial features — all derived purely from `latitude`/`longitude` (and the
internal `junction_name`/`police_station` columns for density features).
No external map/road-network data (ADR-001).

Spatial index: H3 (ADR-002), resolution 9 (~174m hexagon edge length).
GeoHash (precision 7, ~153m x 153m cell) is computed alongside for
comparison/familiarity but is not the primary key features are built on.

Leakage note: `hotspot_frequency`, `violation_density`, `junction_density`,
and `police_station_density` are all computed as **expanding counts using
only rows strictly before the current row's `created_datetime`**, per
ADR-006. They are NOT static full-dataset counts — a row from the dataset's
first day will correctly show near-zero values here, even if its cell turns
out to be very busy later. Requires the input to be sorted by
`created_datetime` before calling `add_spatial_features`.
"""

from __future__ import annotations

import h3
import pandas as pd
import pygeohash as pgh

H3_RESOLUTION = 9
GEOHASH_PRECISION = 7


def add_h3_geohash(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["h3_cell"] = [
        h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
        for lat, lon in zip(df["latitude"], df["longitude"])
    ]
    df["geohash"] = [
        pgh.encode(lat, lon, precision=GEOHASH_PRECISION)
        for lat, lon in zip(df["latitude"], df["longitude"])
    ]
    return df


def _expanding_unique_count(sorted_df: pd.DataFrame, group_col: str, value_col: str) -> pd.Series:
    """For each row (sorted_df must already be sorted by created_datetime),
    count of distinct `value_col` values seen in `group_col`'s group strictly
    before this row. Vectorized via first-occurrence flags + cumulative sum,
    minus the current row's own contribution.
    """
    first_occurrence = (
        sorted_df.groupby(group_col)[value_col]
        .transform(lambda s: (~s.duplicated()).astype(int))
    )
    cumulative_incl_self = first_occurrence.groupby(sorted_df[group_col]).cumsum()
    return cumulative_incl_self - first_occurrence


def add_spatial_density_features(df: pd.DataFrame) -> pd.DataFrame:
    """Requires `h3_cell` (call add_h3_geohash first) and `created_datetime`.
    Sorts internally by created_datetime to guarantee leakage-safety, then
    restores the original row order before returning.
    """
    df = df.copy()
    original_index = df.index
    sorted_df = df.sort_values("created_datetime", kind="stable")

    # hotspot_frequency: count of prior violations in this h3 cell (cumcount
    # on a time-sorted group is exactly "number of rows before me in this group").
    sorted_df["hotspot_frequency"] = sorted_df.groupby("h3_cell").cumcount()

    # violation_density: hotspot_frequency normalized into a rate (violations
    # per day observed so far in this cell) so a cell seen for 1 day with 5
    # violations isn't ranked below a cell seen for 30 days with 20.
    first_seen = sorted_df.groupby("h3_cell")["created_datetime"].transform("min")
    elapsed_days = (sorted_df["created_datetime"] - first_seen).dt.total_seconds() / 86400.0
    elapsed_days_safe = elapsed_days.where(elapsed_days != 0, other=pd.NA)
    sorted_df["violation_density"] = (
        (sorted_df["hotspot_frequency"] / elapsed_days_safe).astype("float64").fillna(0.0)
    )

    # junction_density / police_station_density: how many *distinct* junctions
    # / police stations have historically logged a violation in this h3 cell —
    # a structural "how spatially mixed is this cell's enforcement context" signal.
    sorted_df["junction_density"] = _expanding_unique_count(sorted_df, "h3_cell", "junction_name")
    sorted_df["police_station_density"] = _expanding_unique_count(sorted_df, "h3_cell", "police_station")

    return sorted_df.loc[original_index]


def add_spatial_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_h3_geohash(df)
    df = add_spatial_density_features(df)
    return df
