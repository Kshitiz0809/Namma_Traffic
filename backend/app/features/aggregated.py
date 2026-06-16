"""
Aggregated historical-risk features — leakage-safe expanding frequency
shares per category (ADR-006). Requires `primary_offence_code` from
cleaning.py.

Definition: for category column C, `{C}_historical_risk` = (number of prior
rows sharing this row's C value) / (total number of prior rows, any
category), both counted strictly before the current row in time order.
This is a 0-1 "share of historical traffic attributable to this category"
score — e.g. if a junction accounts for 8% of all violations seen so far,
its historical_risk is ~0.08 at that point in time. It naturally starts at 0
for the very first rows (no history yet) and stabilizes as more data
accumulates, which is realistic for a live system that's still warming up.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RISK_CATEGORY_COLUMNS = {
    "junction_name": "junction_historical_risk",
    "primary_offence_code": "offence_historical_risk",
    "vehicle_type": "vehicle_type_historical_risk",
    "center_code": "center_code_historical_risk",
}


def _historical_risk(sorted_df: pd.DataFrame, category_col: str) -> pd.Series:
    category_prior_count = sorted_df.groupby(category_col).cumcount().astype("float64")
    overall_prior_count = np.arange(len(sorted_df), dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        risk = category_prior_count / overall_prior_count
    risk = pd.Series(risk, index=sorted_df.index).fillna(0.0)
    risk[overall_prior_count == 0] = 0.0
    return risk


def add_historical_risk_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    original_index = df.index
    sorted_df = df.sort_values("created_datetime", kind="stable")

    for category_col, out_col in RISK_CATEGORY_COLUMNS.items():
        sorted_df[out_col] = _historical_risk(sorted_df, category_col)

    return sorted_df.loc[original_index]
