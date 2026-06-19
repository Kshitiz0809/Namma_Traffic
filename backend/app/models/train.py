"""
Phase 3 orchestrator: trains everything, runs the required ablation
experiments, saves models + SHAP + leaderboard/results docs.

Run directly: `python -m app.models.train`
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from app.models.classifier import build_classification_dataset, evaluate_classifier, train_all_classifiers
from app.models.congestion_score import compute_congestion_score, fit_minmax
from app.models.experiments import run_all_experiments
from app.models.explain import compute_shap_values, shap_feature_importance
from app.models.feature_set import NUMERIC_FEATURES, REDUCED_SPATIAL_CATEGORICAL_FEATURES, prepare_model_frame
from app.models.regressor import train_all_regressors
from app.models.risk_score import fit_risk_params
from app.models.spatial_holdout import run_spatial_holdout_test

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # models/ -> app/ -> backend/ -> repo root
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
DOCS_DIR = PROJECT_ROOT / "docs"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def _save_model(model, name: str, model_type: str) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if model_type == "catboost":
        path = MODELS_DIR / f"{name}.cbm"
        model.save_model(str(path))
    elif model_type == "lightgbm":
        path = MODELS_DIR / f"{name}.txt"
        model.booster_.save_model(str(path))
    elif model_type == "xgboost":
        path = MODELS_DIR / f"{name}.json"
        model.save_model(str(path))
    else:
        raise ValueError(model_type)
    return path


def run() -> dict:
    t0 = time.time()
    logger.info("Loading features + targets...")
    features = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    targets = pd.read_parquet(PROCESSED_DIR / "targets.parquet")

    # --- Primary objective: target_hotspot_60m classification ---
    logger.info("Building classification split...")
    cls_split = build_classification_dataset(features, targets, "target_hotspot_60m")
    logger.info("Split:\n%s", cls_split.summary())

    # categorical_features=REDUCED_SPATIAL_CATEGORICAL_FEATURES (drops raw
    # h3_cell/geohash identity, ADR-019/020): the spatial holdout test found
    # the model memorizing cell IDs (h3_cell was the #1 SHAP feature) rather
    # than generalizing. h3_cell itself stays in cls_split.train/val/test as
    # a column (still needed for serving lookups and for the spatial holdout
    # test's own cell-based grouping) — it's just no longer a model input.
    logger.info("Training classifiers (CatBoost -> LightGBM -> XGBoost)...")
    cls_results = train_all_classifiers(cls_split, categorical_features=REDUCED_SPATIAL_CATEGORICAL_FEATURES)
    for name, r in cls_results.items():
        logger.info("%s val metrics: %s", name, r["val_metrics"].to_dict())

    winner_name = max(cls_results, key=lambda n: cls_results[n]["val_metrics"].pr_auc)
    winner_model = cls_results[winner_name]["model"]
    logger.info("Classification winner (by val PR-AUC): %s", winner_name)

    # Touch test set exactly once, with the already-chosen winner.
    feature_cols = NUMERIC_FEATURES + REDUCED_SPATIAL_CATEGORICAL_FEATURES
    X_test = cls_split.test[feature_cols]
    y_test = cls_split.test["target_hotspot_60m"].to_numpy()
    test_proba = winner_model.predict_proba(X_test)[:, 1]
    test_metrics = evaluate_classifier(
        winner_name, y_test, test_proba,
        threshold=cls_results[winner_name]["val_metrics"].best_threshold,
    )
    logger.info("Classification winner TEST metrics: %s", test_metrics.to_dict())

    # --- Secondary objective: target_count_60m regression ---
    logger.info("Building regression split...")
    reg_split = build_classification_dataset(features, targets, "target_count_60m")
    logger.info("Training regressors...")
    reg_results = train_all_regressors(reg_split, categorical_features=REDUCED_SPATIAL_CATEGORICAL_FEATURES)
    for name, r in reg_results.items():
        logger.info("%s val metrics: %s", name, r["val_metrics"].to_dict())
    reg_winner_name = min(reg_results, key=lambda n: reg_results[n]["val_metrics"].mae)

    # --- SHAP on the winning classifier ---
    logger.info("Computing SHAP for %s...", winner_name)
    shap_values, X_sample = compute_shap_values(winner_model, cls_split.val[feature_cols])
    importance = shap_feature_importance(shap_values, feature_cols)
    logger.info("Top 10 SHAP features:\n%s", importance.head(10).to_string(index=False))

    # --- Required ablation experiments A-D ---
    logger.info("Running ablation experiments A-D...")
    experiment_results = run_all_experiments(features, targets)

    # --- Congestion score (derived, reported only — ADR-011) ---
    # cls_split.train/val/test only carry the model_frame columns (NUMERIC_FEATURES
    # + CATEGORICAL_FEATURES), not congestion_score's source columns directly from
    # the full features table — so we re-select the same TIME WINDOW from
    # `features` (rather than reusing cls_split.train) and fit scale params on that.
    logger.info("Computing congestion_score...")
    train_window = features[features["created_datetime"] <= cls_split.train["created_datetime"].max()]
    minmax_params = fit_minmax(train_window)
    congestion = compute_congestion_score(features, minmax_params)
    congestion_out = pd.concat([features[["id", "h3_cell", "created_datetime"]], congestion], axis=1)
    congestion_out.to_parquet(PROCESSED_DIR / "congestion_score.parquet", index=False)
    logger.info("congestion_score distribution:\n%s", congestion["congestion_score"].describe())

    # --- Risk score params (weights/bands/min-max) — fit, not hardcoded ---
    # ADR-021: replaces the old hand-picked WEIGHTS/RISK_BANDS module
    # constants. Fit on the SAME train_window used above, against
    # target_count_60m (the closest available outcome proxy in this dataset
    # — there's no ground-truth congestion data to fit against directly).
    logger.info("Fitting risk_score params (weights/bands/min-max) on train window...")
    reg_winner_model = reg_results[reg_winner_name]["model"]
    risk_fit_df = train_window.merge(targets[["id", "target_count_60m"]], on="id")
    X_risk = prepare_model_frame(risk_fit_df, NUMERIC_FEATURES, REDUCED_SPATIAL_CATEGORICAL_FEATURES)
    risk_hotspot_proba = winner_model.predict_proba(X_risk)[:, 1]
    risk_predicted_count = reg_winner_model.predict(X_risk)
    risk_params = fit_risk_params(
        risk_hotspot_proba, risk_predicted_count, risk_fit_df, risk_fit_df["target_count_60m"],
    )
    with open(MODELS_DIR / "risk_params.json", "w", encoding="utf-8") as f:
        json.dump(asdict(risk_params), f, indent=2)
    logger.info("Fitted risk weights: %s | band cutoffs: %s", risk_params.weights, risk_params.band_cutoffs)

    # --- Spatial generalization check (ADR-016/019/020) ---
    # Re-run on every retrain so docs/spatial_holdout_result.json (read by
    # GET /metrics) always reflects the CURRENT feature set's actual
    # measured behavior, not a one-time number frozen in source.
    logger.info("Running spatial holdout test...")
    holdout_result = run_spatial_holdout_test(features, targets)
    holdout_result.pop("seen_metrics", None)
    holdout_result.pop("unseen_metrics", None)
    with open(DOCS_DIR / "spatial_holdout_result.json", "w", encoding="utf-8") as f:
        json.dump(holdout_result, f, indent=2, default=str)
    logger.info("Spatial holdout verdict: %s (drop %.2f%%)", holdout_result["verdict"], holdout_result["pr_auc_drop_pct"])

    # --- Save winning models ---
    saved_paths = {}
    for name, r in cls_results.items():
        saved_paths[f"classifier_{name}"] = str(_save_model(r["model"], f"classifier_{name}", name))
    for name, r in reg_results.items():
        saved_paths[f"regressor_{name}"] = str(_save_model(r["model"], f"regressor_{name}", name))

    elapsed = time.time() - t0
    logger.info("Phase 3 training complete in %.1fs", elapsed)

    return {
        "classification": {
            "val_metrics": {n: r["val_metrics"].to_dict() for n, r in cls_results.items()},
            "winner": winner_name,
            "test_metrics": test_metrics.to_dict(),
        },
        "regression": {
            "val_metrics": {n: r["val_metrics"].to_dict() for n, r in reg_results.items()},
            "winner": reg_winner_name,
        },
        "shap_importance": importance,
        "experiments": experiment_results,
        "risk_params": asdict(risk_params),
        "spatial_holdout": holdout_result,
        "saved_models": saved_paths,
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    results = run()
    print(json.dumps({k: v for k, v in results.items() if k != "shap_importance"}, indent=2, default=str))
