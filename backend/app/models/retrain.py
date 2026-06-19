"""
Retraining orchestrator — the piece that turns "rerun some scripts by hand
and redeploy" into a single callable entrypoint the admin API can trigger.

Order matters: archive current artifacts (rollback safety) -> rebuild
features from the current master raw CSV -> retrain models (which, per
ADR-019/021, also refits the spatial-robust feature set and the risk score
params as part of `train.run()`) -> refresh the alerts/leaderboard
artifacts the dashboard reads. Each step is itself a plain `run()` function
already used standalone (`python -m app.features.build_features`, etc.) —
this module only sequences them and handles the archive/rollback bookkeeping
that's new.
"""

from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from app.features import build_features
from app.models import generate_phase5_artifacts, train

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
DOCS_DIR = PROJECT_ROOT / "docs"
ARCHIVE_DIR = MODELS_DIR / "archive"


def _archive_current_artifacts() -> str | None:
    """Copies the current ml/models/ + docs/leaderboard.csv into a
    timestamped archive folder before they're overwritten, so a bad retrain
    can be manually rolled back by copying the archived files back. Returns
    the archive path, or None if there was nothing to archive yet (first
    ever training run).
    """
    if not MODELS_DIR.exists() or not any(MODELS_DIR.glob("*.cbm")):
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = ARCHIVE_DIR / stamp
    dest.mkdir(parents=True, exist_ok=True)

    for path in MODELS_DIR.iterdir():
        if path.is_file():
            shutil.copy2(path, dest / path.name)

    leaderboard = DOCS_DIR / "leaderboard.csv"
    if leaderboard.exists():
        shutil.copy2(leaderboard, dest / leaderboard.name)

    logger.info("Archived current model artifacts to %s", dest)
    return str(dest)


def run_pipeline(raw_csv_path: str | Path | None = None) -> dict:
    """Full retrain: archive -> rebuild features -> retrain models (incl.
    risk params + spatial holdout, see train.run()) -> refresh alerts.json.
    `raw_csv_path` defaults to the master raw CSV maintained by
    `app.ingestion.raw_store` (passed in by the admin endpoint that calls
    this after an ingest).
    """
    t0 = time.time()
    archive_path = _archive_current_artifacts()

    logger.info("Rebuilding features from %s...", raw_csv_path or "default raw path")
    build_features.run(raw_csv_path)

    logger.info("Retraining models...")
    train_results = train.run()

    logger.info("Refreshing Phase 5 artifacts (alerts.json)...")
    artifacts_summary = generate_phase5_artifacts.run()

    elapsed = time.time() - t0
    logger.info("Retrain pipeline complete in %.1fs", elapsed)

    return {
        "archive_path": archive_path,
        "classification": train_results["classification"],
        "regression": train_results["regression"],
        "risk_params": train_results["risk_params"],
        "spatial_holdout": train_results["spatial_holdout"],
        "alerts_summary": artifacts_summary,
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    summary = run_pipeline()
    print(json.dumps(summary, indent=2, default=str))
