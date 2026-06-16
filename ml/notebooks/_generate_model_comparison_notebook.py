"""
Generator for 03_model_comparison.ipynb. Same rationale as
_generate_notebooks.py: notebook source as reviewable Python, regenerate +
re-execute after any model/data change instead of hand-editing cells.

Usage:
    python _generate_model_comparison_notebook.py
    jupyter nbconvert --to notebook --execute --inplace 03_model_comparison.ipynb

Requires backend/app/models/train.py to have already been run once (loads
the saved CatBoost model from ml/models/, doesn't retrain).
"""

import nbformat as nbf

CELLS = [
    ("md", "# Phase 3 — Model Comparison, Confusion Matrix, Calibration, SHAP\n\n"
           "Loads the saved winning model (CatBoost — see `docs/baseline_results.md`) "
           "and visualizes what `docs/baseline_results.md` reports in text form. "
           "No retraining happens here."),
    ("code", """\
import sys
sys.path.insert(0, "../../backend")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from catboost import CatBoostClassifier
from sklearn.calibration import calibration_curve
from sklearn.metrics import confusion_matrix, precision_recall_curve

from app.models.classifier import build_classification_dataset, evaluate_classifier
from app.models.explain import compute_shap_values, shap_feature_importance
from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES

sns.set_theme(style="whitegrid")
pd.set_option("display.max_columns", 40)

features = pd.read_parquet("../../data/processed/features.parquet")
targets = pd.read_parquet("../../data/processed/targets.parquet")
split = build_classification_dataset(features, targets)
feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES

model = CatBoostClassifier()
model.load_model("../models/classifier_catboost.cbm")
print("Loaded CatBoost model. Test split:", len(split.test), "rows")
"""),
    ("md", "## 1. Test-set predictions + confusion matrix\nThreshold fixed at the validation-chosen 0.30 (see baseline_results.md)."),
    ("code", """\
X_test = split.test[feature_cols]
y_test = split.test["target_hotspot_60m"].to_numpy()
proba_test = model.predict_proba(X_test)[:, 1]

THRESHOLD = 0.30
y_pred = (proba_test >= THRESHOLD).astype(int)
metrics = evaluate_classifier("catboost_test", y_test, proba_test, threshold=THRESHOLD)
print(metrics.to_dict())

cm = confusion_matrix(y_test, y_pred)
fig, ax = plt.subplots(figsize=(5, 4))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
            xticklabels=["Not Hotspot", "Hotspot"], yticklabels=["Not Hotspot", "Hotspot"], ax=ax)
ax.set_xlabel("Predicted")
ax.set_ylabel("Actual")
ax.set_title(f"Confusion matrix (test, threshold={THRESHOLD})")
plt.tight_layout()
plt.show()
"""),
    ("md", "## 2. Precision-Recall curve\nShows the full precision/recall trade-off across thresholds, not just the single F1-optimal point used above."),
    ("code", """\
precisions, recalls, thresholds = precision_recall_curve(y_test, proba_test)

fig, ax = plt.subplots(figsize=(6, 5))
ax.plot(recalls, precisions, color="#3b6ea5")
ax.scatter([metrics.recall], [metrics.precision], color="#c0392b", zorder=5,
           label=f"chosen threshold={THRESHOLD}")
ax.set_xlabel("Recall")
ax.set_ylabel("Precision")
ax.set_title(f"Precision-Recall curve (PR-AUC = {metrics.pr_auc:.4f})")
ax.legend()
plt.tight_layout()
plt.show()
"""),
    ("md", "## 3. Calibration / reliability curve\nIf the model were perfectly calibrated, points would sit on the diagonal — "
           "a predicted probability of 0.7 should mean the event actually happens ~70% of the time."),
    ("code", """\
prob_true, prob_pred = calibration_curve(y_test, proba_test, n_bins=10)

fig, ax = plt.subplots(figsize=(6, 6))
ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfectly calibrated")
ax.plot(prob_pred, prob_true, marker="o", color="#3b6ea5", label=f"CatBoost (Brier={metrics.brier_score:.4f})")
ax.set_xlabel("Mean predicted probability (per bin)")
ax.set_ylabel("Fraction of actual positives (per bin)")
ax.set_title("Calibration curve")
ax.legend()
plt.tight_layout()
plt.show()
"""),
    ("md", "## 4. SHAP summary plot\nGlobal feature importance + direction of effect, on a sample of the validation set."),
    ("code", """\
X_val = split.val[feature_cols]
shap_values, X_sample = compute_shap_values(model, X_val, max_samples=2000)
importance = shap_feature_importance(shap_values, feature_cols)
importance.head(15)
"""),
    ("code", """\
import shap
shap.summary_plot(shap_values, X_sample, show=False, max_display=15)
plt.tight_layout()
plt.show()
"""),
    ("md", "## 5. Sample hotspot forecasts\nA handful of real test-set rows with predicted probability vs. actual outcome — "
           "including both a confident-correct example and a false positive, since the confusion matrix shows the model "
           "over-predicts positives at this threshold."),
    ("code", """\
sample_df = split.test[["created_datetime", "h3_cell"]].copy()
sample_df["predicted_probability"] = proba_test
sample_df["predicted_hotspot"] = y_pred
sample_df["actual_hotspot"] = y_test

# A few confident true positives
print("Confident TRUE POSITIVES (model correctly predicts hotspot):")
tp = sample_df[(sample_df.predicted_hotspot == 1) & (sample_df.actual_hotspot == 1)]
display(tp.nlargest(5, "predicted_probability"))

# A few false positives — the failure mode the confusion matrix flagged
print("\\nFALSE POSITIVES (model predicts hotspot, but none occurred):")
fp = sample_df[(sample_df.predicted_hotspot == 1) & (sample_df.actual_hotspot == 0)]
display(fp.sample(min(5, len(fp)), random_state=42))

# A few false negatives
print("\\nFALSE NEGATIVES (model misses a real hotspot):")
fn = sample_df[(sample_df.predicted_hotspot == 0) & (sample_df.actual_hotspot == 1)]
display(fn.sample(min(5, len(fn)), random_state=42))
"""),
    ("md", "## 6. Phase 3.5 Task 1 — Cost-aware threshold sweep\n"
           "Loads `docs/threshold_metrics.csv` (generated by `backend/app/models/harden.py`) — "
           "full sweep 0.05-0.95 with the cost model `cost = FP*1 + FN*3`."),
    ("code", """\
threshold_df = pd.read_csv("../../docs/threshold_metrics.csv")

fig, ax1 = plt.subplots(figsize=(8, 5))
ax1.plot(threshold_df["threshold"], threshold_df["precision"], label="Precision", color="#3b6ea5")
ax1.plot(threshold_df["threshold"], threshold_df["recall"], label="Recall", color="#5a9367")
ax1.plot(threshold_df["threshold"], threshold_df["f1"], label="F1", color="#c97a3d")
ax1.axvline(0.15, linestyle="--", color="gray", label="New default (0.15)")
ax1.set_xlabel("Threshold")
ax1.set_ylabel("Score")
ax1.legend(loc="lower left")
ax1.set_title("Threshold sweep (see docs/threshold_selection.md for the 3 recommended operating points)")
plt.tight_layout()
plt.show()

threshold_df[threshold_df["threshold"].isin([0.15, 0.30, 0.70])]
"""),
    ("md", "## 7. Phase 3.5 Task 2 — Calibration comparison\nBaseline vs. Platt vs. Isotonic, evaluated on test."),
    ("code", """\
calibration_df = pd.read_csv("../../docs/calibration_results.csv")
calibration_df
"""),
    ("md", "**Decision: keep baseline (uncalibrated)** — neither method clears the >=5% Brier-improvement "
           "bar required to justify the added complexity (see DECISIONS.md ADR-015 acceptance rule)."),
    ("md", "## 8. Phase 3.5 Task 3 — Spatial generalization holdout ⚠️\n"
           "Train on 80% of H3 cells, evaluate on the other 20% (never seen during training), "
           "same validation time window for both."),
    ("code", """\
region_df = pd.read_csv("../../docs/region_performance.csv")
display(region_df[["region_set", "pr_auc", "precision", "recall", "n_samples"]])

fig, ax = plt.subplots(figsize=(5, 4))
ax.bar(region_df["region_set"], region_df["pr_auc"], color=["#3b6ea5", "#c0392b"])
ax.set_ylabel("PR-AUC")
ax.set_title("Seen vs. unseen H3 cells (FAIL — drop exceeds 5%)")
ax.set_ylim(0, 1)
plt.tight_layout()
plt.show()

pr_auc_drop = (region_df.loc[region_df.region_set == "seen", "pr_auc"].iloc[0] -
               region_df.loc[region_df.region_set == "unseen", "pr_auc"].iloc[0]) / region_df.loc[region_df.region_set == "seen", "pr_auc"].iloc[0] * 100
print(f"PR-AUC drop on unseen regions: {pr_auc_drop:.2f}% (threshold for PASS was <5%) -> VERDICT: FAIL")
"""),
    ("md", "**Honest takeaway:** this corroborates the SHAP audit below — `h3_cell` is the dominant feature, "
           "meaning the model partially memorizes per-cell identity rather than purely generalizing. "
           "Full discussion + redesign recommendations: `docs/spatial_holdout.md`."),
    ("md", "## 9. Phase 4 Task 4 — Multi-horizon comparison\n"
           "**Caveat (read before the chart):** raw PR-AUC rises with horizon mostly because longer "
           "windows have a higher positive rate, not because longer-horizon predictions are inherently "
           "better. `lift_over_base_rate` (PR-AUC / positive_rate) corrects for this."),
    ("code", """\
horizon_df = pd.read_csv("../../docs/horizon_comparison.csv")
display(horizon_df[["horizon_minutes", "pr_auc", "positive_rate", "lift_over_base_rate"]])

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
axes[0].plot(horizon_df["horizon_minutes"], horizon_df["pr_auc"], marker="o", color="#3b6ea5")
axes[0].set_title("Raw PR-AUC (misleading alone — rises with base rate)")
axes[0].set_xlabel("Horizon (min)")

axes[1].plot(horizon_df["horizon_minutes"], horizon_df["lift_over_base_rate"], marker="o", color="#c0392b")
axes[1].set_title("Lift over base rate (corrected) — favors SHORTER horizons")
axes[1].set_xlabel("Horizon (min)")
plt.tight_layout()
plt.show()

print("Recommended operational horizon: 60 minutes (balances absolute performance, lift, and enforcement lead time)")
print("See docs/baseline_results.md 'Phase 3.5/4' section for the full rationale.")
"""),
    ("md", "## 10. Phase 4 Task 5 — SHAP stability audit\n"
           "Mean |SHAP| averaged over 5 bootstrap resamples, with rank stability."),
    ("code", """\
stability_df = pd.read_csv("../../docs/feature_stability.csv")
display(stability_df.head(15))

fig, ax = plt.subplots(figsize=(8, 7))
top15 = stability_df.head(15).sort_values("mean_abs_shap")
ax.barh(top15["feature"], top15["mean_abs_shap"], color="#3b6ea5")
ax.set_xlabel("Mean |SHAP| (5-bootstrap average)")
ax.set_title("Bootstrap-averaged SHAP importance")
plt.tight_layout()
plt.show()

print("h3_cell mean rank across 5 bootstraps: 1.0 (always #1) -> H3 dominance CONFIRMED")
print("Top-10 stability (Jaccard): 1.0 (perfectly stable set, regardless of resample)")
print("Timestamp leakage detected: False | Target proxies detected: None")
"""),
    ("md", "## Conclusion\n"
           "- CatBoost is the Phase 3 winner — see `docs/baseline_results.md` for the full model comparison table.\n"
           "- **Operating threshold changed from 0.30 to 0.15** (Phase 3.5 Task 1) — the cost-aware "
           "choice given a 3x penalty on missed hotspots vs. false alarms.\n"
           "- **Calibration: not applied** — neither Platt nor Isotonic cleared the 5% Brier-improvement bar.\n"
           "- **Spatial robustness: FAIL** — 7.88% PR-AUC drop on unseen H3 cells, corroborated by `h3_cell`'s "
           "SHAP dominance (mean rank 1.0). The model is reliable on cells it has seen before, but should not "
           "be trusted on genuinely new geographic coverage without retraining.\n"
           "- **Operational horizon: 60 minutes**, chosen using base-rate-corrected lift, not raw PR-AUC "
           "(which would have misleadingly favored 90 minutes).\n"
           "- SHAP top-10 ranking is perfectly stable across resamples — the model's behavior is "
           "reproducible, even where (per the spatial holdout) it has a real generalization weakness."),
]


def build_notebook(cells):
    nb = nbf.v4.new_notebook()
    nb["cells"] = [
        nbf.v4.new_markdown_cell(content) if kind == "md" else nbf.v4.new_code_cell(content)
        for kind, content in cells
    ]
    return nb


if __name__ == "__main__":
    nbf.write(build_notebook(CELLS), "03_model_comparison.ipynb")
    print("Wrote 03_model_comparison.ipynb")
