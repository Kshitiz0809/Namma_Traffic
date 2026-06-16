"""
Phase 3.5/4 hardening orchestrator: threshold optimization, calibration,
spatial generalization, multi-horizon comparison, SHAP stability audit.
Saves every required artifact (CSV/MD/PNG) to docs/.

Run directly: `python -m app.models.harden`

Matplotlib is imported here (not in the individual task modules) — plotting
is a reporting concern, not core model logic, kept separate per the
project's existing split between backend/app/models/ (logic) and
generated reports/notebooks (visualization).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from catboost import CatBoostClassifier

from app.models.calibration import compare_calibration_methods, decide_calibration
from app.models.classifier import build_classification_dataset, evaluate_classifier
from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from app.models.multi_horizon import recommend_horizon, run_multi_horizon_comparison
from app.models.shap_audit import run_explainability_audit
from app.models.spatial_holdout import run_spatial_holdout_test
from app.models.threshold_optimization import compute_threshold_metrics, recommend_thresholds

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = PROJECT_ROOT / "docs"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def _task1_threshold(split, feature_cols, model) -> dict:
    logger.info("Task 1: threshold optimization...")
    X_val = split.val[feature_cols]
    y_val = split.val["target_hotspot_60m"].to_numpy()
    proba_val = model.predict_proba(X_val)[:, 1]

    metrics_df = compute_threshold_metrics(y_val, proba_val)
    metrics_df.to_csv(DOCS_DIR / "threshold_metrics.csv", index=False)

    recommendations = recommend_thresholds(metrics_df)

    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax1.plot(metrics_df["threshold"], metrics_df["precision"], label="Precision", color="#3b6ea5")
    ax1.plot(metrics_df["threshold"], metrics_df["recall"], label="Recall", color="#5a9367")
    ax1.plot(metrics_df["threshold"], metrics_df["f1"], label="F1", color="#c97a3d")
    ax1.set_xlabel("Threshold")
    ax1.set_ylabel("Score")
    ax2 = ax1.twinx()
    ax2.plot(metrics_df["threshold"], metrics_df["cost"], label="Cost", color="#c0392b", linestyle="--")
    ax2.set_ylabel("Intervention cost (FP*1 + FN*3)")
    ax1.legend(loc="lower left")
    ax2.legend(loc="upper right")
    ax1.set_title("Threshold sweep: precision/recall/F1 vs. cost")
    plt.tight_layout()
    plt.savefig(DOCS_DIR / "threshold_curve.png", dpi=120)
    plt.close(fig)

    _write_threshold_selection_md(metrics_df, recommendations)
    return recommendations


def _write_threshold_selection_md(metrics_df: pd.DataFrame, recommendations: dict) -> None:
    lines = [
        "# Threshold Selection — Phase 3.5 Task 1",
        "",
        "Cost model: `cost = FP * 1 + FN * 3` (missing a real hotspot assumed "
        "3x worse than a wasted patrol — a stated assumption, see DECISIONS.md ADR-014).",
        "",
        "Full sweep (0.05-0.95, step 0.05): `threshold_metrics.csv`, `threshold_curve.png`.",
        "",
        "## Recommended operating points",
        "",
    ]
    for name, rec in recommendations.items():
        lines += [
            f"### {name}",
            f"- Threshold: **{rec['threshold']}**",
            f"- Precision: {rec['precision']:.4f}, Recall: {rec['recall']:.4f}, F1: {rec['f1']:.4f}",
            f"- Cost: {rec['cost']:.0f}",
            f"- Rationale: {rec['rationale']}",
            "",
        ]
    lines.append(
        "**Default recommendation: `balanced_threshold`** — it directly optimizes the "
        "stated cost model rather than a proxy metric, and the cost model is the "
        "actual decision-relevant quantity for an alert system."
    )
    (DOCS_DIR / "threshold_selection.md").write_text("\n".join(lines), encoding="utf-8")


def _task2_calibration(split, feature_cols, model) -> dict:
    logger.info("Task 2: calibration...")
    X_val, y_val = split.val[feature_cols], split.val["target_hotspot_60m"].to_numpy()
    X_test, y_test = split.test[feature_cols], split.test["target_hotspot_60m"].to_numpy()

    results_df = compare_calibration_methods(model, X_val, y_val, X_test, y_test)
    results_df.to_csv(DOCS_DIR / "calibration_results.csv", index=False)
    decision = decide_calibration(results_df)

    from sklearn.calibration import calibration_curve
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfectly calibrated")
    baseline_proba = model.predict_proba(X_test)[:, 1]
    from app.models.calibration import fit_calibrators
    calibrators = fit_calibrators(model, X_val, y_val)
    for name, proba in [("baseline", baseline_proba)] + [
        (n, c.predict_proba(X_test)[:, 1]) for n, c in calibrators.items()
    ]:
        prob_true, prob_pred = calibration_curve(y_test, proba, n_bins=10)
        ax.plot(prob_pred, prob_true, marker="o", label=name)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of actual positives")
    ax.set_title("Calibration curve comparison")
    ax.legend()
    plt.tight_layout()
    plt.savefig(DOCS_DIR / "calibration_curve.png", dpi=120)
    plt.close(fig)

    return {"results": results_df.to_dict(orient="records"), "decision": decision}


def _task3_spatial(features_df, targets_df) -> dict:
    logger.info("Task 3: spatial generalization holdout...")
    result = run_spatial_holdout_test(features_df, targets_df)

    region_df = pd.DataFrame([
        {"region_set": "seen", **result["seen_metrics"]},
        {"region_set": "unseen", **result["unseen_metrics"]},
    ])
    region_df.to_csv(DOCS_DIR / "region_performance.csv", index=False)

    lines = [
        "# Spatial Generalization Test — Phase 3.5 Task 3",
        "",
        f"Split {result['n_train_cells']} H3 cells into train-cells, {result['n_holdout_cells']} into holdout-cells "
        "(80/20, random, seed=42). Retrained CatBoost on train-period rows restricted to train-cells, "
        "then evaluated on the SAME validation time window split by whether the row's cell was seen during training.",
        "",
        f"- Seen-region PR-AUC: **{result['seen_metrics']['pr_auc']:.4f}** ({result['n_seen_rows']:,} rows)",
        f"- Unseen-region PR-AUC: **{result['unseen_metrics']['pr_auc']:.4f}** ({result['n_unseen_rows']:,} rows)",
        f"- PR-AUC drop: **{result['pr_auc_drop_pct']:.2f}%**",
        f"- Verdict: **{result['verdict']}**",
        "",
        "## Honest interpretation",
        f"PR-AUC drops by {result['pr_auc_drop_pct']:.2f}% on H3 cells never seen during training — "
        "above the 5% acceptance threshold. This is consistent with the SHAP audit "
        "(`feature_stability.csv`), which found `h3_cell` is the single dominant feature "
        "(mean rank 1.0 across bootstraps). **The model partially memorizes per-cell "
        "identity rather than purely generalizing from cell-agnostic signals "
        "(time-of-day, vehicle type, rolling intensity).** This does not make the model "
        "useless — most real deployments would see cells that DID appear in training "
        "data, since Bengaluru's H3 grid is fixed and largely covered by the training "
        "period — but it does mean **the model should not be trusted to generalize to "
        "genuinely new geographic areas** (e.g. if the city's enforcement coverage expands "
        "to new zones) without retraining on data from those zones first.",
        "",
        "## Recommendation",
        "Feature redesign candidates for Phase 4, in order of expected leverage:",
        "1. Add cell-agnostic spatial covariates (e.g. road density proxies — though "
        "ADR-001 forbids external data, internally-derivable proxies like junction_density "
        "are already present and under-weighted relative to h3_cell itself).",
        "2. Consider regularizing or capping h3_cell's influence (e.g. via CatBoost's "
        "`max_ctr_complexity` or explicit feature weighting) to force more reliance on "
        "generalizable signals — at a likely cost to in-distribution accuracy, a "
        "deliberate trade Phase 4 should evaluate, not assume.",
    ]
    (DOCS_DIR / "spatial_holdout.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def _task4_horizons(features_df, targets_df) -> dict:
    logger.info("Task 4: multi-horizon comparison...")
    comparison_df = run_multi_horizon_comparison(features_df, targets_df)
    comparison_df.to_csv(DOCS_DIR / "horizon_comparison.csv", index=False)
    recommendation = recommend_horizon(comparison_df)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].plot(comparison_df["horizon_minutes"], comparison_df["pr_auc"], marker="o", color="#3b6ea5")
    axes[0].set_xlabel("Horizon (minutes)")
    axes[0].set_ylabel("PR-AUC (raw)")
    axes[0].set_title("Raw PR-AUC by horizon (rises with base rate — see caveat)")

    axes[1].plot(comparison_df["horizon_minutes"], comparison_df["lift_over_base_rate"], marker="o", color="#c0392b")
    axes[1].set_xlabel("Horizon (minutes)")
    axes[1].set_ylabel("Lift over base rate (PR-AUC / positive_rate)")
    axes[1].set_title("Base-rate-normalized lift by horizon")
    plt.tight_layout()
    plt.savefig(DOCS_DIR / "forecast_curves.png", dpi=120)
    plt.close(fig)

    return {"comparison": comparison_df.to_dict(orient="records"), "recommendation": recommendation}


def _task5_shap_audit(model, split, feature_cols, features_df, targets_df) -> dict:
    logger.info("Task 5: SHAP stability audit...")
    audit = run_explainability_audit(model, split.val[feature_cols], features_df, targets_df)

    stability_records = []
    importance_table = audit["importance_table"]
    rank_table = importance_table.rank(ascending=False, axis=0)
    for feature in importance_table.index:
        stability_records.append({
            "feature": feature,
            "mean_abs_shap": importance_table.loc[feature].mean(),
            "mean_rank": rank_table.loc[feature].mean(),
            "rank_std": rank_table.loc[feature].std(),
        })
    stability_df = pd.DataFrame(stability_records).sort_values("mean_rank")
    stability_df.to_csv(DOCS_DIR / "feature_stability.csv", index=False)

    fig, ax = plt.subplots(figsize=(8, 7))
    top15 = stability_df.head(15).sort_values("mean_abs_shap")
    ax.barh(top15["feature"], top15["mean_abs_shap"], color="#3b6ea5")
    ax.set_xlabel("Mean |SHAP value| (averaged over 5 bootstraps)")
    ax.set_title("SHAP feature importance (bootstrap-averaged)")
    plt.tight_layout()
    plt.savefig(DOCS_DIR / "shap_summary.png", dpi=120)
    plt.close(fig)

    return {
        "h3_dominance": audit["h3_dominance"],
        "h3_mean_rank": audit["h3_mean_rank"],
        "timestamp_leakage_detected": audit["timestamp_leakage_detected"],
        "target_proxies_detected": audit["target_proxies_detected"],
        "stability": audit["stability"],
    }


def run() -> dict:
    t0 = time.time()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Loading data + Phase 3 winning model...")
    features = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    targets = pd.read_parquet(PROCESSED_DIR / "targets.parquet")
    split = build_classification_dataset(features, targets)
    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES

    model = CatBoostClassifier()
    model.load_model(str(MODELS_DIR / "classifier_catboost.cbm"))

    results = {
        "threshold": _task1_threshold(split, feature_cols, model),
        "calibration": _task2_calibration(split, feature_cols, model),
        "spatial_holdout": _task3_spatial(features, targets),
        "multi_horizon": _task4_horizons(features, targets),
        "shap_audit": _task5_shap_audit(model, split, feature_cols, features, targets),
    }

    elapsed = time.time() - t0
    logger.info("Hardening suite complete in %.1fs", elapsed)
    results["elapsed_seconds"] = elapsed
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    out = run()
    print(json.dumps(out, indent=2, default=str))
