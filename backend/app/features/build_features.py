"""
Pipeline orchestrator: raw CSV -> cleaned + feature-engineered parquet +
targets parquet. This is the only module that wires the feature modules
together in order — each module stays independently testable/importable.

Run directly: `python -m app.features.build_features`
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.features.aggregated import add_historical_risk_features
from app.features.cleaning import clean
from app.features.operational import add_operational_features
from app.features.outliers import flag_outlier_coordinates
from app.features.rolling import add_rolling_features
from app.features.spatial import add_spatial_features
from app.features.targets import add_targets
from app.features.temporal import add_temporal_features
from app.ingestion.load_data import load_raw_violations

logger = logging.getLogger(__name__)

FEATURES_OUTPUT_PATH = "data/processed/features.parquet"
TARGETS_OUTPUT_PATH = "data/processed/targets.parquet"


def build_feature_table(df: pd.DataFrame) -> pd.DataFrame:
    """Run every feature module in dependency order. Rows with a missing
    `created_datetime` (5 in the audit) are dropped ONLY here, at the feature
    stage, because every single time-based feature module requires it — the
    raw/cleaned data still keeps them (see ingestion/cleaning, which never
    drop). This is the one explicit, documented exception to "never drop".
    """
    n_before = len(df)
    df = df.dropna(subset=["created_datetime"]).copy()
    n_dropped = n_before - len(df)
    if n_dropped:
        logger.warning(
            "Dropped %d/%d rows with missing created_datetime before feature "
            "engineering (time-based features have no defined value without it)",
            n_dropped, n_before,
        )

    df = clean(df)
    df = flag_outlier_coordinates(df)
    df = add_spatial_features(df)
    df = add_temporal_features(df)
    df = add_operational_features(df)
    df = add_rolling_features(df)
    df = add_historical_risk_features(df)
    return df


def run(raw_csv_path: str | Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    t0 = time.time()
    logger.info("Loading raw data...")
    raw_df = load_raw_violations(raw_csv_path)

    logger.info("Building feature table...")
    features_df = build_feature_table(raw_df)
    logger.info("Features built in %.1fs — shape %s", time.time() - t0, features_df.shape)

    t1 = time.time()
    logger.info("Building target table...")
    targets_df = add_targets(features_df)
    logger.info("Targets built in %.1fs — shape %s", time.time() - t1, targets_df.shape)

    features_out = settings.processed_data_full_path.parent / "features.parquet"
    targets_out = settings.processed_data_full_path.parent / "targets.parquet"
    features_out.parent.mkdir(parents=True, exist_ok=True)

    features_df.to_parquet(features_out, index=False)
    targets_df.to_parquet(targets_out, index=False)
    logger.info("Wrote %s and %s", features_out, targets_out)

    return features_df, targets_df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    features, targets = run()
    print(f"\nFeatures: {features.shape}")
    print(features.dtypes)
    print(f"\nTargets: {targets.shape}")
    print(targets.describe())
