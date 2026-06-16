"""
Time-based train/validation/test split. See DECISIONS.md ADR-010 for why
this must never be a random split.

Train = earliest 70% of rows (by created_datetime), validation = next 15%,
test = latest 15%. Split by row count after time-sorting (not by calendar
date) since monthly volume is uneven (44k-66k rows/month per
docs/data_quality_report.md) — a date-based split could give wildly
different split sizes.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
# TEST_FRAC is the remainder (0.15)


@dataclass
class TimeSplit:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame

    def summary(self) -> str:
        def _range(df: pd.DataFrame) -> str:
            if len(df) == 0:
                return "empty"
            return f"{df['created_datetime'].min()} -> {df['created_datetime'].max()} ({len(df):,} rows)"

        return (
            f"train: {_range(self.train)}\n"
            f"val:   {_range(self.val)}\n"
            f"test:  {_range(self.test)}"
        )


def time_based_split(df: pd.DataFrame, train_frac: float = TRAIN_FRAC, val_frac: float = VAL_FRAC) -> TimeSplit:
    sorted_df = df.sort_values("created_datetime", kind="stable").reset_index(drop=True)
    n = len(sorted_df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    return TimeSplit(
        train=sorted_df.iloc[:train_end].copy(),
        val=sorted_df.iloc[train_end:val_end].copy(),
        test=sorted_df.iloc[val_end:].copy(),
    )
