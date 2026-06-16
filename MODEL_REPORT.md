# Model Report

Tracks every model trained, its metrics, and the comparison decision made at
each modeling phase. Empty until Phase 3 — created now so the structure
exists and each phase appends to it rather than reinventing the format.

---

## How to read this report

Each entry follows the same structure: **what was trained, on what data, how
it scored, what was decided, and why.** Metrics are never reported without
the split they came from (train/val/test, and which dates) — a number with
no context about leakage-safety or evaluation window is not trustworthy.

---

## Phase 3 — Spatial Prediction Engine (not started)

Planned: CatBoost → LightGBM → XGBoost baselines (DECISIONS.md ADR-008) on
`target_hotspot_60m`, using `data/processed/features.parquet`. Time-based
train/val/test split (not random — random splits leak future information
into training via the leakage-safe-but-still-time-correlated rolling
features). SHAP explainability on the winning model.

| Model | Precision | Recall | F1 | Notes |
|---|---|---|---|---|
| _(pending)_ | | | | |

## Phase 4 — Temporal Forecast Engine (not started)

Planned: baseline → XGBoost → optional LSTM on `target_count_15m/30m/60m`.

| Model | Horizon | MAE | RMSE | Notes |
|---|---|---|---|---|
| _(pending)_ | | | | |

## Phase 5+ — Congestion Impact / Alert Engine (not started)

Not a trained model — rule-based scoring service. Reported here only if it
ends up calibrated against historical outcomes.
