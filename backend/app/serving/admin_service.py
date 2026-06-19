"""
Admin API — closes the "frozen model, no way to retrain on new data" gap.

Police (or ops) can POST a new violations CSV and trigger a retrain without
redeploying. The heavy lifting lives in `app.ingestion.raw_store` (dedupe +
append) and `app.models.retrain` (the actual pipeline); this module only
exposes them over HTTP with:
- a minimal shared-secret auth guard (`X-Admin-Token`) — these routes can
  overwrite production models, so they must not be reachable unauthenticated.
- async job tracking via FastAPI `BackgroundTasks` + an in-memory job dict
  (no Celery/APScheduler needed at this scale — neither is a project
  dependency, and a single in-process background task is enough for one
  retrain at a time).
- hot-reloading the serving layer's cached models/params on success, so a
  running process picks up a retrained model without a restart.

Known limitation (documented, not hidden): on ephemeral-filesystem hosts
(Render/HF Space free tier), `data/raw/violations_master.csv` and retrained
artifacts won't survive a redeploy unless a persistent volume is attached.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi import Header

from app.core.config import settings
from app.ingestion.load_data import load_raw_violations
from app.ingestion.raw_store import MASTER_RAW_PATH, append_new_violations, load_master
from app.models import retrain
from app.serving import forecast_service, metrics_service, risk_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_jobs: dict[str, "RetrainJob"] = {}


@dataclass
class RetrainJob:
    job_id: str
    status: str = "PENDING"  # PENDING | RUNNING | SUCCESS | FAILED
    result: dict | None = None
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None


def _require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_api_token:
        raise HTTPException(status_code=503, detail="Admin API disabled (set ADMIN_API_TOKEN to enable).")
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Token header.")


@router.post("/ingest", dependencies=[Depends(_require_admin)])
async def ingest(file: UploadFile):
    """Validate + dedupe + append a new violations CSV to the master raw
    dataset (does NOT retrain by itself — call /admin/retrain after, or in
    the same workflow, to actually incorporate the new rows into the model).
    """
    raw_bytes = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = Path(tmp.name)

    try:
        # Re-load through the same typed/parsed path as the original
        # dataset (explicit dtypes + datetime parsing in load_raw_violations)
        # rather than trusting the upload's raw string dtypes.
        new_df = load_raw_violations(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse uploaded CSV: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    result = append_new_violations(new_df)
    return {
        "rows_received": result.rows_received,
        "rows_added": result.rows_added,
        "rows_duplicate": result.rows_duplicate,
        "rows_invalid": result.rows_invalid,
        "invalid_reasons": result.invalid_reasons,
        "master_row_count": result.master_row_count,
    }


def _run_retrain_job(job_id: str) -> None:
    job = _jobs[job_id]
    job.status = "RUNNING"
    try:
        load_master()  # ensure the master file exists (seeds from original CSV if first run)
        result = retrain.run_pipeline(raw_csv_path=MASTER_RAW_PATH)
        job.result = result
        job.status = "SUCCESS"
        # Hot-reload the serving layer so the running process picks up the
        # new models/params/parquet without a restart.
        forecast_service.reload_state()
        risk_snapshot.reload_state()
        metrics_service.reload_state()
        logger.info("Retrain job %s succeeded in %.1fs", job_id, result["elapsed_seconds"])
    except Exception as exc:  # noqa: BLE001 — surface any failure via job status, not a crashed background task
        job.status = "FAILED"
        job.error = str(exc)
        logger.exception("Retrain job %s failed", job_id)
    finally:
        job.finished_at = datetime.now(timezone.utc).isoformat()


@router.post("/retrain", dependencies=[Depends(_require_admin)])
def trigger_retrain(background_tasks: BackgroundTasks):
    """Kicks off the full retrain pipeline (rebuild features from the
    master raw CSV -> retrain models -> refit risk params -> re-check
    spatial holdout -> refresh alerts.json) in the background. Returns
    immediately with a job_id to poll via GET /admin/retrain/{job_id}.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = RetrainJob(job_id=job_id)
    background_tasks.add_task(_run_retrain_job, job_id)
    return {"job_id": job_id, "status": "PENDING"}


@router.get("/retrain/{job_id}", dependencies=[Depends(_require_admin)])
def get_retrain_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id.")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "result": job.result,
        "error": job.error,
    }
