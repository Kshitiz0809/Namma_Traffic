"""
Schema definition + validation for the raw violations dataset.

Why validate explicitly instead of trusting the CSV?
- Hackathon datasets get re-exported/edited by hand; columns get renamed/dropped silently.
- Every downstream phase (feature engineering, ML, API) assumes these columns exist.
  Failing loudly here, at ingestion, is much cheaper than debugging a KeyError in Phase 3.
"""

from dataclasses import dataclass, field

# Exact columns we expect, in the order they appear in the source CSV.
EXPECTED_COLUMNS: list[str] = [
    "id",
    "latitude",
    "longitude",
    "location",
    "vehicle_number",
    "vehicle_type",
    "description",
    "violation_type",
    "offence_code",
    "created_datetime",
    "closed_datetime",
    "modified_datetime",
    "device_id",
    "created_by_id",
    "center_code",
    "police_station",
    "data_sent_to_scita",
    "junction_name",
    "action_taken_timestamp",
    "data_sent_to_scita_timestamp",
    "updated_vehicle_number",
    "updated_vehicle_type",
    "validation_status",
    "validation_timestamp",
]

# Columns that MUST be non-null for a row to be usable for spatial/ML work.
# (Other columns may legitimately be NULL, e.g. closed_datetime for open cases.)
REQUIRED_NON_NULL = ["id", "latitude", "longitude", "created_datetime"]

# Columns parsed as datetimes during load.
DATETIME_COLUMNS = [
    "created_datetime",
    "closed_datetime",
    "modified_datetime",
    "action_taken_timestamp",
    "data_sent_to_scita_timestamp",
    "validation_timestamp",
]

# Bengaluru's approximate bounding box — used as a sanity check on lat/lon,
# not a hard filter. Rows outside this box are flagged, not silently dropped.
LAT_RANGE = (12.7, 13.2)
LON_RANGE = (77.3, 77.9)


@dataclass
class SchemaValidationResult:
    is_valid: bool
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    null_counts: dict[str, int] = field(default_factory=dict)
    out_of_bounds_coords: int = 0
    total_rows: int = 0

    def summary(self) -> str:
        lines = [
            f"Schema valid: {self.is_valid}",
            f"Total rows: {self.total_rows}",
        ]
        if self.missing_columns:
            lines.append(f"MISSING columns (breaks pipeline): {self.missing_columns}")
        if self.extra_columns:
            lines.append(f"Extra/unexpected columns (informational): {self.extra_columns}")
        if self.null_counts:
            lines.append("Nulls in required columns:")
            for col, count in self.null_counts.items():
                lines.append(f"  - {col}: {count}")
        lines.append(f"Coordinates outside Bengaluru bbox: {self.out_of_bounds_coords}")
        return "\n".join(lines)


def validate_schema(df) -> SchemaValidationResult:
    """Validate a loaded DataFrame against the expected dataset contract."""
    columns = list(df.columns)
    missing = [c for c in EXPECTED_COLUMNS if c not in columns]
    extra = [c for c in columns if c not in EXPECTED_COLUMNS]

    null_counts = {}
    for col in REQUIRED_NON_NULL:
        if col in columns:
            null_counts[col] = int(df[col].isna().sum())

    out_of_bounds = 0
    if "latitude" in columns and "longitude" in columns:
        lat_ok = df["latitude"].between(*LAT_RANGE)
        lon_ok = df["longitude"].between(*LON_RANGE)
        out_of_bounds = int((~(lat_ok & lon_ok)).sum())

    is_valid = len(missing) == 0

    return SchemaValidationResult(
        is_valid=is_valid,
        missing_columns=missing,
        extra_columns=extra,
        null_counts=null_counts,
        out_of_bounds_coords=out_of_bounds,
        total_rows=len(df),
    )
