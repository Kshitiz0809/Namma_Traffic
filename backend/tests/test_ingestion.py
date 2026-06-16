"""
Phase 1 tests: prove the ingestion module loads the real dataset and that
schema validation correctly flags problems on a deliberately broken sample.
"""

import pandas as pd
import pytest

from app.ingestion.load_data import load_and_validate
from app.ingestion.schema import EXPECTED_COLUMNS, validate_schema


def test_real_dataset_loads_and_is_schema_valid():
    """End-to-end smoke test against the actual CSV in data/raw/."""
    df, result = load_and_validate()

    assert len(df) > 0
    assert result.is_valid, f"Schema invalid: {result.summary()}"
    assert result.missing_columns == []
    # We expect very few/no rows missing required fields in the real dataset.
    assert result.null_counts.get("id", 0) == 0


def test_validate_schema_flags_missing_columns():
    broken_df = pd.DataFrame({"id": ["1"], "latitude": [12.9], "longitude": [77.6]})
    result = validate_schema(broken_df)

    assert not result.is_valid
    assert "violation_type" in result.missing_columns
    assert "created_datetime" in result.missing_columns


def test_validate_schema_flags_out_of_bounds_coordinates():
    df = pd.DataFrame({col: ["x"] for col in EXPECTED_COLUMNS})
    df["latitude"] = [40.0]  # New York, not Bengaluru
    df["longitude"] = [-74.0]

    result = validate_schema(df)
    assert result.out_of_bounds_coords == 1


def test_validate_schema_counts_nulls_in_required_columns():
    df = pd.DataFrame({col: ["x", "x"] for col in EXPECTED_COLUMNS})
    df["latitude"] = [12.9, None]
    df["longitude"] = [77.6, 77.6]

    result = validate_schema(df)
    assert result.null_counts["latitude"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
