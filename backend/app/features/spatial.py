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


def add_neighbor_averaged_features(
    df: pd.DataFrame, value_cols: list[str], ring: int = 1, prefix: str = "neighbor_"
) -> pd.DataFrame:
    """Average each of `value_cols` across a cell's H3 ring-`ring` neighbors,
    evaluated as of each row's own `created_datetime` ("how hot is the
    surrounding neighborhood right now", not just this exact cell). Unlike
    raw `h3_cell` identity, this is genuinely transferable to a cell the
    model has never seen during training — a new cell surrounded by
    historically hot neighbors still carries signal, which raw cell-ID
    categorical encoding cannot provide (ADR-019/ADR-020
    spatial-generalization fix).

    Leakage-safe by construction: every column in `value_cols` must itself
    already be a leakage-safe expanding/windowed feature (computed using
    only each row's own history strictly before it — true of
    `hotspot_frequency`, `violation_density`, `junction_density`,
    `police_station_density`, `rolling_hotspot_intensity`,
    `violations_last_15m` etc. in this codebase). This function only looks
    up a neighbor's most recent *already leakage-safe* value as of the same
    timestamp (via `merge_asof(direction="backward")`), so it never reaches
    into the future relative to the row being featurized. Callable at any
    point in the pipeline once `value_cols` exist — used once right after
    `add_spatial_density_features` (this module) and once more after
    `add_rolling_features` (rolling.py), since those features don't exist
    yet at the spatial stage.

    Requires `h3_cell` and `created_datetime` to already exist on `df`.
    """
    df = df.copy()
    original_index = df.index
    row_id_col = "_row_id"
    sorted_df = df.sort_values("created_datetime", kind="stable").copy()
    sorted_df[row_id_col] = sorted_df.index

    unique_cells = sorted_df["h3_cell"].unique()
    neighbor_map = {cell: [n for n in h3.grid_disk(cell, ring) if n != cell] for cell in unique_cells}

    history = (
        sorted_df[["h3_cell", "created_datetime", *value_cols]]
        .rename(columns={"h3_cell": "neighbor_cell"})
        .sort_values("created_datetime", kind="stable")
    )

    exploded = sorted_df[[row_id_col, "h3_cell", "created_datetime"]].copy()
    exploded["neighbor_cell"] = exploded["h3_cell"].map(neighbor_map)
    exploded = exploded.explode("neighbor_cell").dropna(subset=["neighbor_cell"])
    exploded = exploded.sort_values("created_datetime", kind="stable")

    merged = pd.merge_asof(
        exploded, history, on="created_datetime", by="neighbor_cell", direction="backward",
    )

    new_cols = {col: f"{prefix}{col}" for col in value_cols}
    neighbor_agg = merged.groupby(row_id_col)[value_cols].mean().rename(columns=new_cols)

    sorted_df = sorted_df.set_index(row_id_col)
    sorted_df[list(new_cols.values())] = neighbor_agg[list(new_cols.values())]
    sorted_df[list(new_cols.values())] = sorted_df[list(new_cols.values())].fillna(0.0)

    return sorted_df.loc[original_index]


NEIGHBOR_SPATIAL_VALUE_COLS = [
    "hotspot_frequency", "violation_density", "junction_density", "police_station_density",
]


def add_spatial_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_h3_geohash(df)
    df = add_spatial_density_features(df)
    df = add_neighbor_averaged_features(df, NEIGHBOR_SPATIAL_VALUE_COLS)
    return df
