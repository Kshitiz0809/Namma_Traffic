"""
Target variables for Phase 3 (spatial hotspot classifier) and Phase 4
(temporal forecast engine). See DECISIONS.md ADR-005 for the definition
rationale and ADR-004 for why this file is kept separate from every other
feature module.

*** THESE COLUMNS USE FUTURE DATA ON PURPOSE. THEY ARE TARGETS, NOT FEATURES. ***
Never join target_*.parquet columns into a training feature matrix. They are
written to a separate file specifically so that mistake requires an
explicit, visible join rather than already being in the same table.

Definitions (all relative to the same h3_cell as the current row):
- target_count_15m / 30m / 60m / 90m: count of OTHER violations in this cell
  in the N minutes strictly AFTER this row's created_datetime (excludes itself).
- target_hotspot_15m / 30m / 60m / 90m: 1 if target_count_Nm > 0, else 0.
  (90m window added in Phase 3.5 Task 4 — multi-horizon comparison.)
"""

from __future__ import annotations

import pandas as pd

TARGET_WINDOWS_MINUTES = [15, 30, 60, 90]


def _forward_count(sorted_df: pd.DataFrame, minutes: int) -> pd.Series:
    """Count of other rows in the same h3_cell within the following `minutes`.
    `sorted_df` must be sorted ascending by created_datetime.

    Implementation trick: count "future" events in normal time by counting
    "past" events in *reversed* time — sort by `reverse_time = max_time - t`
    ascending (equivalent to original time descending), then a standard
    backward-looking `rolling(window, closed='left')` count in reverse-time
    space is exactly a forward-looking count in original time space.

    Note: each group's original row labels are preserved through the
    groupby (via `g.index`) rather than re-indexing by the reverse-time
    value — duplicate timestamps within a cell would otherwise collide and
    silently misalign results onto the wrong rows.
    """
    max_time = sorted_df["created_datetime"].max()
    rev = sorted_df.copy()
    rev["_reverse_time"] = max_time - rev["created_datetime"]
    rev = rev.sort_values("_reverse_time", kind="stable")

    def _per_group(g: pd.DataFrame) -> pd.Series:
        s = g.set_index("_reverse_time")["id"].rolling(f"{minutes}min", closed="left").count()
        s.index = g.index
        return s

    counts = rev.groupby("h3_cell", group_keys=False).apply(_per_group, include_groups=False)
    return counts.reindex(sorted_df.index).fillna(0)


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a NEW DataFrame containing only `id` + the target columns —
    deliberately not merged into the features table by this function. Callers
    decide how/when to join, making any future-data usage an explicit step.
    """
    sorted_df = df.sort_values("created_datetime", kind="stable")
    targets = pd.DataFrame(index=df.index)
    targets["id"] = df["id"]

    for minutes in TARGET_WINDOWS_MINUTES:
        col = f"target_count_{minutes}m"
        targets[col] = _forward_count(sorted_df, minutes).reindex(df.index)

    for minutes in TARGET_WINDOWS_MINUTES:
        targets[f"target_hotspot_{minutes}m"] = (targets[f"target_count_{minutes}m"] > 0).astype(int)
    return targets
