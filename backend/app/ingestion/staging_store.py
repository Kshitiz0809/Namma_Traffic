"""
Staging area for police-uploaded CSVs — sits between "a file got uploaded"
and "the master dataset (and therefore the model) changed."

Why a separate stage instead of `raw_store.append_new_violations` directly
on upload: real police-submitted data should be reviewable before it's
allowed to influence retraining, and retraining itself should stay a
deliberate, separate action that can batch up several approved uploads —
not something that fires automatically per upload. `raw_store.py` keeps
owning the master file and the actual dedupe/append logic; this module only
owns the pending/approved/rejected lifecycle and reuses that logic once a
staged upload is approved.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.ingestion import raw_store
from app.ingestion.load_data import load_raw_violations
from app.ingestion.schema import validate_schema

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STAGING_DIR = PROJECT_ROOT / "data" / "raw" / "staging"

PREVIEW_ROW_COUNT = 5


@dataclass
class StagingRecord:
    staging_id: str
    original_filename: str
    uploaded_at: str
    status: str  # PENDING | APPROVED | REJECTED
    row_count: int
    schema_valid: bool
    missing_columns: list[str] = field(default_factory=list)
    null_counts: dict[str, int] = field(default_factory=dict)
    resolved_at: str | None = None
    merge_result: dict | None = None
    reject_reason: str | None = None

    def _dir(self) -> Path:
        return STAGING_DIR / self.staging_id

    def csv_path(self) -> Path:
        return self._dir() / "violations.csv"

    def meta_path(self) -> Path:
        return self._dir() / "meta.json"

    def save(self) -> None:
        self.meta_path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def _load_record(staging_dir: Path) -> StagingRecord:
    data = json.loads((staging_dir / "meta.json").read_text(encoding="utf-8"))
    return StagingRecord(**data)


def stage_upload(df: pd.DataFrame, original_filename: str) -> StagingRecord:
    """Stores an uploaded CSV as a PENDING staging record. Does NOT reject
    schema-invalid files outright — they're staged with `schema_valid:
    false` so a human reviewer can see exactly why and decide to reject,
    rather than the upload silently failing.
    """
    validation = validate_schema(df)
    staging_id = uuid.uuid4().hex[:12]
    record = StagingRecord(
        staging_id=staging_id,
        original_filename=original_filename,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        status="PENDING",
        row_count=len(df),
        schema_valid=validation.is_valid,
        missing_columns=validation.missing_columns,
        null_counts=validation.null_counts,
    )
    record._dir().mkdir(parents=True, exist_ok=True)
    df.to_csv(record.csv_path(), index=False)
    record.save()
    logger.info("Staged upload %s (%s, %d rows, schema_valid=%s)",
                staging_id, original_filename, len(df), validation.is_valid)
    return record


def list_staged() -> list[StagingRecord]:
    if not STAGING_DIR.exists():
        return []
    records = [_load_record(d) for d in sorted(STAGING_DIR.iterdir()) if d.is_dir()]
    return sorted(records, key=lambda r: r.uploaded_at, reverse=True)


def get_staged(staging_id: str) -> StagingRecord | None:
    staging_dir = STAGING_DIR / staging_id
    if not staging_dir.exists():
        return None
    return _load_record(staging_dir)


def get_preview_rows(record: StagingRecord) -> list[dict]:
    df = pd.read_csv(record.csv_path(), nrows=PREVIEW_ROW_COUNT, dtype=str)
    return df.fillna("").to_dict(orient="records")


def approve_staged(staging_id: str) -> raw_store.AppendResult | None:
    """Merges a PENDING staged upload into the master raw dataset via the
    existing `raw_store.append_new_violations` (not reimplemented here),
    then marks the staging record APPROVED with the merge result attached.
    Returns None if the staging_id doesn't exist or isn't PENDING.
    """
    record = get_staged(staging_id)
    if record is None or record.status != "PENDING":
        return None

    # Re-load through the same typed/parsed path as the master file itself
    # (explicit dtypes + datetime parsing) so concatenation in
    # append_new_violations doesn't mix typed and raw-string columns.
    staged_df = load_raw_violations(record.csv_path())
    result = raw_store.append_new_violations(staged_df)

    record.status = "APPROVED"
    record.resolved_at = datetime.now(timezone.utc).isoformat()
    record.merge_result = asdict(result)
    record.save()

    logger.info("Approved staging %s -> %d rows added to master", staging_id, result.rows_added)
    return result


def reject_staged(staging_id: str, reason: str | None = None) -> StagingRecord | None:
    """Marks a PENDING staged upload REJECTED. The file is kept on disk for
    audit — rejection never deletes data, it just excludes it from the
    master dataset.
    """
    record = get_staged(staging_id)
    if record is None or record.status != "PENDING":
        return None

    record.status = "REJECTED"
    record.resolved_at = datetime.now(timezone.utc).isoformat()
    record.reject_reason = reason
    record.save()

    logger.info("Rejected staging %s (reason=%s)", staging_id, reason)
    return record
