"""
Cleaning step: parse the raw dataset's quirks into usable types.

Per ADR-007 in DECISIONS.md, this step never drops rows. It only parses,
flags, and derives — so every downstream feature module can assume clean
types without re-deriving them, and nothing here forecloses a later decision
to filter (that's a model-training-time choice, made with evidence from
Phase 3 comparisons, not baked in silently here).
"""

from __future__ import annotations

import ast
import logging

import pandas as pd

logger = logging.getLogger(__name__)


def _parse_stringified_list(value) -> list:
    """Parse columns like '["WRONG PARKING","NO PARKING"]' or '[112,104]' into
    real Python lists. Falls back to an empty list for null/unparseable values
    rather than raising, since a handful of malformed rows shouldn't crash
    the whole pipeline (the count of fallbacks is logged so it's not silent).
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = ast.literal_eval(value)
        return parsed if isinstance(parsed, list) else [parsed]
    except (ValueError, SyntaxError):
        return []


def parse_violation_lists(df: pd.DataFrame) -> pd.DataFrame:
    """Parse `violation_type` and `offence_code` stringified-JSON-list columns
    into real lists, plus convenience scalar columns (`primary_violation_type`,
    `primary_offence_code`, `num_offences`) for models/features that want a
    single category rather than a list.
    """
    df = df.copy()

    df["violation_type_list"] = df["violation_type"].apply(_parse_stringified_list)
    df["offence_code_list"] = df["offence_code"].apply(_parse_stringified_list)

    n_unparseable = int((df["violation_type_list"].apply(len) == 0).sum())
    if n_unparseable:
        logger.warning(
            "%d rows had an empty/unparseable violation_type list (kept, not dropped)",
            n_unparseable,
        )

    df["num_offences"] = df["violation_type_list"].apply(len)
    df["primary_violation_type"] = df["violation_type_list"].apply(
        lambda lst: lst[0] if lst else "UNKNOWN"
    )
    df["primary_offence_code"] = df["offence_code_list"].apply(
        lambda lst: str(lst[0]) if lst else "UNKNOWN"
    )
    return df


def flag_duplicate_vehicle_events(df: pd.DataFrame) -> pd.DataFrame:
    """Flag (don't drop) rows sharing the same (vehicle_number, created_datetime) —
    9,521 such rows found in the audit. Could be multiple genuine simultaneous
    offences for one vehicle, or duplicate logging; we don't have enough info
    to tell automatically, so we flag and let Phase 3 evaluate both ways.
    """
    df = df.copy()
    has_both = df["vehicle_number"].notna() & df["created_datetime"].notna()
    dup_mask = pd.Series(False, index=df.index)
    if has_both.any():
        subset = df.loc[has_both]
        dup_mask.loc[has_both] = subset.duplicated(
            subset=["vehicle_number", "created_datetime"], keep=False
        )
    df["is_duplicate_vehicle_event"] = dup_mask
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Run the full cleaning step. Order matters: list-parsing before anything
    that reads `primary_violation_type`, duplicate-flagging last since it's
    independent.
    """
    df = parse_violation_lists(df)
    df = flag_duplicate_vehicle_events(df)
    return df
