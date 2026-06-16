"""
FastAPI entrypoint.

Phase 1: app boots, health check confirms the raw dataset is reachable.
Phase 5: /forecast goes live (app/serving/forecast_service.py). Remaining
endpoints (/heatmap, /alerts, /recommendation as dedicated routes) land in
Phase 8 once the dashboard needs them directly.
"""

import logging

from fastapi import FastAPI

from app.core.config import settings
from app.ingestion.load_data import load_and_validate
from app.serving.forecast_service import router as forecast_router

logging.basicConfig(level=settings.log_level, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Parking Intelligence + Predictive Alert Platform",
    version="0.1.0",
    description="Predicts where/when parking violations and congestion occur, and recommends enforcement action.",
)

app.include_router(forecast_router)


@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "env": settings.app_env,
        "status": "ok",
        "phase": "1 - project setup + data ingestion",
    }


@app.get("/health")
def health():
    """Liveness check + a cheap sanity check that the dataset is reachable and valid.

    Note: this re-reads the full CSV on every call, which is fine for a Phase 1
    smoke test but too slow for production use. From Phase 2 onward, the API
    reads pre-processed parquet/Postgres data instead of the raw CSV directly.
    """
    try:
        df, validation = load_and_validate()
        return {
            "status": "ok" if validation.is_valid else "degraded",
            "rows_loaded": validation.total_rows,
            "schema_valid": validation.is_valid,
            "missing_columns": validation.missing_columns,
        }
    except FileNotFoundError as e:
        return {"status": "error", "detail": str(e)}
