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
    ("md", "## Conclusion\n"
           "- CatBoost is the Phase 3 winner — see `docs/baseline_results.md` for the full model comparison table.\n"
           "- The model is recall-leaning at the chosen threshold: it rarely misses a real hotspot, "
           "at the cost of a high false-positive rate. Phase 6's alert engine needs to decide the "
           "right operating point given the real-world cost of a missed vs. a wasted patrol.\n"
           "- Calibration is moderate (Brier ≈ 0.18, not near 0) — predicted probabilities are "
           "directionally useful but not exact percentages without further calibration work.\n"
           "- SHAP confirms `h3_cell` and `rolling_hotspot_intensity` as the dominant signals, "
           "consistent with Experiment D in `docs/baseline_results.md` showing rolling features "
           "measurably outperform raw counts alone."),
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
