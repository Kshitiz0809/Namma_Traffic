"""
Load the raw violations CSV into a validated pandas DataFrame.

Scope for Phase 1: load + parse + validate only. No cleaning/feature engineering
yet (that's Phase 2) — this module's only job is "can we trust this file enough
to build on top of it".
"""

import logging
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.ingestion.schema import DATETIME_COLUMNS, validate_schema

logger = logging.getLogger(__name__)

# Dtypes for columns we know the type of ahead of time.
# Everything else loads as `object` (string) until Phase 2 decides how to parse it
# (e.g. violation_type / offence_code are stringified JSON lists in the source data).
DTYPES = {
    "id": "string",
    "latitude": "float64",
    "longitude": "float64",
    "location": "string",
    "vehicle_number": "string",
    "vehicle_type": "string",
    "description": "string",
    "violation_type": "string",
    "offence_code": "string",
    "device_id": "string",
    "created_by_id": "string",
    "center_code": "string",
    "police_station": "string",
    "data_sent_to_scita": "string",
    "junction_name": "string",
    "updated_vehicle_number": "string",
    "updated_vehicle_type": "string",
    "validation_status": "string",
}


def load_raw_violations(path: str | Path | None = None) -> pd.DataFrame:
    """Load the raw CSV with explicit dtypes and parsed datetime columns.

    Note: the source CSV uses the literal string "NULL" for missing values
    (not an empty cell), so we tell pandas to treat that as NaN explicitly.
    """
    csv_path = Path(path) if path else settings.raw_data_full_path
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Raw dataset not found at {csv_path}. "
            f"Place the CSV there or set RAW_DATA_PATH in your .env."
        )

    logger.info("Loading raw violations CSV from %s", csv_path)
    df = pd.read_csv(
        csv_path,
        dtype=DTYPES,
        na_values=["NULL", "null", ""],
        keep_default_na=True,
    )

    for col in DATETIME_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))
    return df


def load_and_validate(path: str | Path | None = None) -> tuple[pd.DataFrame, "SchemaValidationResult"]:  # noqa: F821
    """Convenience entrypoint: load the CSV and run schema validation against it."""
    df = load_raw_violations(path)
    result = validate_schema(df)
    return df, result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    dataframe, validation = load_and_validate()
    print(validation.summary())
    if not validation.is_valid:
        raise SystemExit(1)
