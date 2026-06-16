"""
Outlier flagging — per ADR-007, flag only, never drop here.

`is_outlier_coordinate` lets Phase 3 run the same model with/without these
168 rows and report the difference, instead of that decision being made
invisibly at feature-engineering time.
"""

import pandas as pd

from app.ingestion.schema import LAT_RANGE, LON_RANGE


def flag_outlier_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lat_ok = df["latitude"].between(*LAT_RANGE)
    lon_ok = df["longitude"].between(*LON_RANGE)
    df["is_outlier_coordinate"] = ~(lat_ok & lon_ok)
    return df
