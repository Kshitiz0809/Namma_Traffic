"""
Persistent "master" raw violations file that admin ingestion appends to —
the gap this closes: the original `violations_raw.csv` (the hackathon-
provided dataset) is treated as a frozen, read-only baseline everywhere
else in the codebase; there was previously no path for police-uploaded new
CSVs to ever reach the training pipeline. This module is the only place
that mutates a raw dataset on disk, and it never touches the original file
— it seeds a separate appendable copy from it on first use.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.ingestion.load_data import load_raw_violations
from app.ingestion.schema import REQUIRED_NON_NULL, validate_schema

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MASTER_RAW_PATH = PROJECT_ROOT / "data" / "raw" / "violations_master.csv"


@dataclass
class AppendResult:
    rows_received: int
    rows_added: int
    rows_duplicate: int
    rows_invalid: int
    invalid_reasons: list[str] = field(default_factory=list)
    master_row_count: int = 0
    master_path: str = str(MASTER_RAW_PATH)


def load_master() -> pd.DataFrame:
    """Returns the master raw dataset, seeding it from the original
    hackathon-provided CSV (`settings.raw_data_full_path`) on first use.
    That original file is read once to seed the appendable copy and is
    never written to.
    """
    if MASTER_RAW_PATH.exists():
        return load_raw_violations(MASTER_RAW_PATH)
    logger.info("Seeding master raw store from %s", settings.raw_data_full_path)
    seed = load_raw_violations(settings.raw_data_full_path)
    MASTER_RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    seed.to_csv(MASTER_RAW_PATH, index=False)
    return seed


def append_new_violations(new_df: pd.DataFrame) -> AppendResult:
    """Validate, dedupe (by `id` against the master file), and append new
    violation rows to the master raw CSV. Returns counts/reasons so the
    admin caller gets a clear report instead of a bare success/failure.
    """
    rows_received = len(new_df)
    validation = validate_schema(new_df)

    if validation.missing_columns:
        # Schema-breaking — reject the whole batch rather than guess at
        # column meaning. Every downstream feature module assumes these
        # columns exist (same rationale as schema.py's own docstring).
        return AppendResult(
            rows_received=rows_received,
            rows_added=0,
            rows_duplicate=0,
            rows_invalid=rows_received,
            invalid_reasons=[f"missing required columns: {validation.missing_columns}"],
            master_row_count=len(load_master()),
        )

    master = load_master()
    new_df = new_df.copy()
    new_df["id"] = new_df["id"].astype("string")
    existing_ids = set(master["id"].astype("string"))

    is_duplicate = new_df["id"].isin(existing_ids)
    rows_duplicate = int(is_duplicate.sum())
    candidates = new_df[~is_duplicate]

    missing_required = candidates[REQUIRED_NON_NULL].isna().any(axis=1)
    rows_invalid = int(missing_required.sum())
    to_add = candidates[~missing_required]

    invalid_reasons = []
    if rows_invalid:
        invalid_reasons.append(f"{rows_invalid} rows missing a required field {REQUIRED_NON_NULL}")

    combined = pd.concat([master, to_add], ignore_index=True)
    combined.to_csv(MASTER_RAW_PATH, index=False)

    logger.info(
        "Ingest: %d received, %d added, %d duplicate, %d invalid -> master now %d rows",
        rows_received, len(to_add), rows_duplicate, rows_invalid, len(combined),
    )

    return AppendResult(
        rows_received=rows_received,
        rows_added=len(to_add),
        rows_duplicate=rows_duplicate,
        rows_invalid=rows_invalid,
        invalid_reasons=invalid_reasons,
        master_row_count=len(combined),
    )
