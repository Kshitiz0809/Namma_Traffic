"""
FastAPI entrypoint.

Phase 1: app boots, health check confirms the raw dataset is reachable.
Phase 5: /forecast goes live (app/serving/forecast_service.py).
Phase 6: /alerts, /metrics added (app/serving/{alerts,metrics}_service.py),
CORS enabled for the Next.js dashboard, full API surface documented in
docs/api_contract.md. OpenAPI docs are FastAPI's built-in /docs and /redoc
— no separate generation step needed, just documented as available.

CORS note: scoped to the deployed Vercel frontend + local dev origins now
that the real frontend URL is known (previously allow_origins=["*"] while
the deployed origin was still TBD).
"""

import logging
from pathlib import Path

import pyarrow.parquet as pq
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.ingestion.load_data import load_and_validate
from app.serving.admin_service import router as admin_router
from app.serving.alerts_service import router as alerts_router
from app.serving.dispatch_service import router as dispatch_router
from app.serving.forecast_service import router as forecast_router
from app.serving.metrics_service import router as metrics_router
from app.serving.replay_service import router as replay_router

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_FEATURES_PATH = PROJECT_ROOT / "data" / "processed" / "features.parquet"

logging.basicConfig(level=settings.log_level, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Parking Intelligence + Predictive Alert Platform",
    version="0.7.0",
    description="Predicts where/when parking violations and congestion occur, and recommends enforcement action.",
)

ALLOWED_ORIGINS = [
    "https://namma-traffic-orpin.vercel.app",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(forecast_router)
app.include_router(alerts_router)
app.include_router(metrics_router)
app.include_router(replay_router)
app.include_router(dispatch_router)
# /admin/* — server-side/ops use only (curl/Postman), not the browser
# dashboard, so it's intentionally outside ALLOWED_ORIGINS/allow_methods
# above. Guarded by its own X-Admin-Token check (admin_service._require_admin),
# disabled entirely unless ADMIN_API_TOKEN is set.
app.include_router(admin_router)


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

    Deployed images (see backend/Dockerfile) don't ship the raw CSV — only
    data/processed/. In that case, fall back to a cheap parquet metadata read
    instead of returning a misleading "error" status for an expected gap.
    """
    try:
        df, validation = load_and_validate()
        return {
            "status": "ok" if validation.is_valid else "degraded",
            "rows_loaded": validation.total_rows,
            "schema_valid": validation.is_valid,
            "missing_columns": validation.missing_columns,
        }
    except FileNotFoundError:
        if PROCESSED_FEATURES_PATH.exists():
            row_count = pq.ParquetFile(PROCESSED_FEATURES_PATH).metadata.num_rows
            return {
                "status": "ok",
                "rows_loaded": row_count,
                "schema_valid": True,
                "missing_columns": [],
                "note": "raw CSV not shipped in this deployment; reporting from data/processed/features.parquet",
            }
        return {"status": "error", "detail": "Neither the raw CSV nor data/processed/features.parquet were found."}
