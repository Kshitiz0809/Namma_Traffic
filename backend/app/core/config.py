"""
Centralized configuration.

Why a config layer (instead of `os.environ.get(...)` scattered everywhere)?
- Single source of truth for every setting the app needs.
- Validates types/required values at startup (fail fast, not 20 minutes into a demo).
- Lets every module (ingestion, API, ML) import `settings` instead of re-reading env vars.

The `.env` file is expected at the project root (one level above `backend/`),
so this works the same whether you run `uvicorn` from `backend/` or the repo root.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is 3 parents up
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_env: str = "development"
    app_name: str = "parking-intelligence"
    log_level: str = "INFO"

    # --- Data ---
    raw_data_path: str = "data/raw/violations_raw.csv"
    processed_data_path: str = "data/processed/processed_data.parquet"

    # --- Postgres ---
    database_url: str = "postgresql://parking:parking_dev_password@localhost:5432/parking_intelligence"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Kafka (Phase 7) ---
    kafka_bootstrap_servers: str = "localhost:9092"

    # --- MLflow (Phase 9) ---
    mlflow_tracking_uri: str = "http://localhost:5000"

    # --- Maps ---
    mapbox_access_token: str = ""

    @property
    def raw_data_full_path(self) -> Path:
        """Resolve raw_data_path relative to the project root, not the CWD."""
        p = Path(self.raw_data_path)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def processed_data_full_path(self) -> Path:
        p = Path(self.processed_data_path)
        return p if p.is_absolute() else PROJECT_ROOT / p


# Instantiated once, imported everywhere: `from app.core.config import settings`
settings = Settings()
