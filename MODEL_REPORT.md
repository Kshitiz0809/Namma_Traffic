# Model Report

Tracks every model trained, its metrics, and the comparison decision made at
each modeling phase. Full numbers/tables: `docs/baseline_results.md` and
`docs/leaderboard.csv` — this file is the running summary across phases.

---

## How to read this report

Each entry follows the same structure: **what was trained, on what data, how
it scored, what was decided, and why.** Metrics are never reported without
the split they came from (train/val/test, and which dates) — a number with
no context about leakage-safety or evaluation window is not trustworthy.

---

## Phase 3 — Spatial Prediction Engine ✅

**Split** (time-based, DECISIONS.md ADR-010): train 2023-11-09→2024-02-19
(208,911 rows), val 2024-02-19→2024-03-14 (44,767 rows), test
2024-03-14→2024-04-08 (44,767 rows).

### Primary objective: `target_hotspot_60m` (binary classification)

| Model | PR-AUC (val) | Precision | Recall | F1 | Brier | Threshold |
|---|---|---|---|---|---|---|
| **CatBoost (winner)** | **0.8767** | 0.7316 | 0.9620 | **0.8311** | **0.1766** | 0.30 |
| LightGBM | 0.8649 | 0.7351 | 0.9505 | 0.8290 | 0.1832 | 0.30 |
| XGBoost | 0.8632 | 0.7245 | 0.9567 | 0.8246 | 0.1918 | 0.20 |

Test (CatBoost, threshold 0.30): PR-AUC 0.8732, Precision 0.7341, Recall
0.9651, F1 0.8339 — tracks validation closely, no overfitting signal.

**Top SHAP features:** `h3_cell` (0.435), `rolling_hotspot_intensity`
(0.240), `vehicle_type` (0.136), `violations_last_15m` (0.099),
`hour_cos` (0.088). Full list + plot: `docs/baseline_results.md`,
`ml/notebooks/03_model_comparison.ipynb`.

**Required ablations (all CatBoost, val PR-AUC):**
| Experiment | Result |
|---|---|
| A. with/without outliers | 0.8767 vs 0.8743 — negligible, kept in |
| B. with/without duplicates | 0.8767 vs 0.8772 — small improvement without, flagged for revisit |
| C. H3 vs GeoHash | 0.8767 vs 0.8759 — H3 marginally better, kept as primary |
| D. raw counts vs full rolling | 0.8701 vs 0.8767 — clearest effect, rolling features kept |

Full discussion + caveats: `docs/baseline_results.md` section 4.

### Secondary objective: `target_count_60m` (regression)

| Model | MAE (val) | RMSE | R² |
|---|---|---|---|
| **CatBoost (winner)** | **5.92** | **10.58** | **0.271** |
| LightGBM | 6.02 | 10.92 | 0.223 |
| XGBoost | 6.24 | 11.18 | 0.186 |

R²=0.27 is real but modest — flagged as a baseline for Phase 4 to beat, not
a finished result.

### Congestion score (derived, NOT a trained target — ADR-011)

`0.5×violation_density + 0.3×rolling_hotspot_intensity + 0.2×police_station_density`,
all min-max scaled on train-period stats. Mean 0.096, median 0.086, max
0.565 (right-skewed, as expected). Saved to `data/processed/congestion_score.parquet`.

### Artifacts
- Models: `ml/models/{classifier,regressor}_{catboost,lightgbm,xgboost}.{cbm,txt,json}`
- `docs/baseline_results.md` — full narrative + confusion matrix + calibration discussion
- `docs/leaderboard.csv` — machine-readable results table
- `ml/notebooks/03_model_comparison.ipynb` — confusion matrix, PR curve, calibration curve, SHAP summary, sample forecasts (TP/FP/FN examples)

### Known limitations (carried into Phase 4+)
- Model is recall-leaning at the F1-optimal threshold (96.5% recall, only
  17.4% true-negative rate) — Phase 6's alert engine must choose its own
  operating threshold based on real intervention cost, not reuse 0.30 blindly.
- Calibration is moderate, not exact (Brier 0.1766) — no calibration layer applied.
- Experiment C (H3 vs GeoHash) only swapped the categorical spatial key, not
  the full set of spatially-derived numeric features — a complete ablation
  would re-derive density/rolling features on a GeoHash grid too.

## Phase 4 — Temporal Forecast Engine (not started)

Planned: extend the `target_count_60m` regression baseline above to the
15/30-minute horizons too (`target_count_15m`, `target_count_30m` already
exist in `targets.parquet`), compare against a naive baseline (e.g.
same-hour-yesterday), consider LSTM only if the gap over the tree-based
baseline justifies it.

## Phase 5+ — Congestion Impact / Alert Engine (not started)

`congestion_score` from Phase 3 is the starting formula. Not yet calibrated
against real outcomes.
