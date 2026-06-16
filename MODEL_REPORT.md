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

## Phase 3.5 — Decision Layer Hardening ✅

Goal: deployability/robustness, not higher validation PR-AUC (explicit
instruction — no model retraining for score-chasing this round). Full
writeup: `docs/baseline_results.md` "Phase 3.5/4" section. Artifacts:
`threshold_metrics.csv`, `threshold_selection.md`, `threshold_curve.png`,
`calibration_results.csv`, `calibration_curve.png`, `spatial_holdout.md`,
`region_performance.csv`, `feature_stability.csv`, `shap_summary.png`.

| Task | Result | Decision |
|---|---|---|
| 1. Cost-aware threshold (FP=1, FN=3) | Min-cost threshold = 0.15 (cost 13,415 vs. 14,624 at old F1-optimal 0.30) | **Switch default threshold 0.30 → 0.15** |
| 2. Calibration (Platt/Isotonic) | Neither clears the ≥5% Brier-improvement bar (Platt +0.66%, Isotonic +1.12%) | **Keep uncalibrated baseline** |
| 3. Spatial holdout (unseen H3 cells) | PR-AUC drop 7.88% (seen 0.8833 vs unseen 0.8137) — **exceeds 5% bar** | **FAIL — flagged as known limitation, not fixed this round** |
| 4. Explainability audit (5 bootstraps) | Top-10 stability 1.0 (perfect); `h3_cell` mean rank 1.0 (always #1) — corroborates Task 3 | Confirms spatial memorization is real, not a fluke |

**Most important finding:** Tasks 3 and 4 independently agree the model
leans on `h3_cell` identity more than is healthy for generalization to new
geography. Not fixed this round (would require feature redesign — see
`docs/spatial_holdout.md` recommendations) — surfaced and documented instead
of hidden, per the instruction to prioritize deployability/honesty over
chasing a better-looking metric.

## Phase 4 — Multi-Horizon Forecast Engine ✅ (initial)

`target_hotspot_15m/30m/60m/90m` all added to `targets.parquet`
(`backend/app/features/targets.py`). Same CatBoost baseline, same
time-based split, trained per horizon (`docs/horizon_comparison.csv`,
`docs/forecast_curves.png`).

| Horizon | PR-AUC (raw) | Positive rate | Lift over base rate |
|---|---|---|---|
| 15m | 0.7834 | 60.5% | **1.294** |
| 30m | 0.8337 | 65.3% | 1.276 |
| 60m | 0.8767 | 70.0% | 1.253 |
| 90m | 0.8929 | 72.4% | 1.234 |

**Critical finding:** raw PR-AUC rises with horizon almost entirely because
longer windows have a higher positive rate, not because longer-horizon
predictions are more skillful — confirmed by `lift_over_base_rate`
(PR-AUC ÷ positive rate), which actually *favors shorter horizons* (15m:
1.294 vs 90m: 1.234), the opposite conclusion from raw PR-AUC alone.

**Recommended operational horizon: 60 minutes** (unchanged) — balances
strong absolute performance, reasonable lift, practical enforcement lead
time, and consistency with `congestion_score`/Phase 3 artifacts already
built around this window. Full rationale: `docs/baseline_results.md`.

## Final robustness check — Reduced-Spatial-Identity Experiment ✅

One last experiment before feature lock (per explicit instruction: single
comparison, no additional variants). Full writeup: `docs/spatial_dependency.md`.

| | PR-AUC | Precision | Recall | F1 |
|---|---|---|---|---|
| Model A (full set, with `h3_cell`) | 0.8767 | 0.7316 | 0.9620 | 0.8311 |
| Model B (`h3_cell`/`geohash` removed) | 0.8719 | 0.7330 | 0.9644 | 0.8329 |

**Drop: 0.55% → Spatial abstraction = PASS** (≤3% bar). Does not contradict
the spatial-holdout FAIL above — that experiment measures cold-start failure
on cells with zero history of ANY kind; this one measures `h3_cell`'s
marginal value for cells the model already has history on, which turns out
to be small because density/rolling/historical-risk features already
capture most of the same signal. **Decision: keep `h3_cell`** — removing it
buys negligible robustness for a real (if small) accuracy cost.

**FEATURE SET IS NOW FROZEN.** `backend/app/models/feature_set.py`'s
`NUMERIC_FEATURES` + `CATEGORICAL_FEATURES` is the locked contract for Phase 5+.

### Final operating recommendation (going into Phase 5)
| Decision | Value |
|---|---|
| Operating threshold | **0.15** (was 0.30) |
| Calibration | None (baseline probabilities) |
| Operational horizon | **60 minutes** |
| Spatial robustness (new-geography generalization) | **FAIL** — model won't generalize to new geographic coverage without retraining. Does NOT block deployment within existing coverage (explicit instruction). |
| Spatial abstraction (h3_cell marginal value) | **PASS** — `h3_cell` kept, feature set frozen |

## Phase 5 — Parking-Induced Congestion Risk Engine ✅

Renamed from "Congestion Impact Engine" per review (estimates risk from
parking behavior, not measured traffic congestion). Full details:
`docs/risk_definition.md`, `docs/recommendation_rules.yaml`, `docs/alerts.json`,
`docs/spatial_dependency.md`'s sibling docs, DECISIONS.md ADR-020.

### Task 1 — Risk score (derived, NOT a new ML target)
```
risk_score = 100 * (0.40*hotspot_probability + 0.30*normalized_predicted_count
                   + 0.20*persistence + 0.10*recent_intensity)
```
Uses the FROZEN Phase 3 classifier + regressor (no retraining). Bands are
**data-driven** (train-period percentiles), not arbitrary round numbers —
fixed 40/60/80 cutoffs were tried first and left CRITICAL empty:

| Band | Score range | Validation population |
|---|---|---|
| LOW | 0-34.0 | 58.1% |
| MEDIUM | 34.0-45.1 | 27.6% |
| HIGH | 45.1-54.2 | 11.9% |
| CRITICAL | 54.2+ | 2.4% |

### Task 2 — Recommendation engine (rule-based YAML, no LLM)
Base action from risk band (Monitor/Patrol/Deploy enforcement/Tow operation
candidate), escalated one level when vehicle mix (high-obstruction types)
AND junction history (named-junction concentration) both support it.
**Data quirk found and worked around**: `junction_name == "No Junction"` is
~49.5% of rows and inflates that category's historical-risk share to ~0.5 —
excluded from the escalation rule, which is calibrated against
named-junctions-only statistics instead.

On the validation set: 64 escalations out of 44,767 rows; recommendation
counts — Monitor 26,013, Patrol 12,281, Deploy enforcement 5,373, Tow
operation candidate 1,100.

### Task 3 — Alert layer
LOW/MEDIUM/HIGH/CRITICAL → GREEN/YELLOW/ORANGE/RED, using the FINAL
(post-escalation) band. Each alert includes zone, probability, risk score,
and top-2 contributing factors (read off the risk_score's own weighted
components). `docs/alerts.json`: 60 representative alerts (20 per
non-LOW level, highest-risk-score first — not an exhaustive log).

### Task 4 — Forecast service (`GET /forecast`)
`backend/app/serving/forecast_service.py`, wired into `backend/app/main.py`.
Accepts `h3_cell` OR `lat`+`lon`, optional `vehicle_type` override. Returns
`hotspot_probability`, `predicted_count`, `congestion_risk`, `risk_band`,
`recommendation`, `confidence` (heuristic: `|probability - 0.5| * 2`, NOT a
calibrated interval per Phase 3.5's calibration findings), plus
`top_contributing_factors` and cold-start handling. Tested via FastAPI
`TestClient` across 4 scenarios (known cell, vehicle-type override, lat/lon
resolution, cold start) — all correct. **Caveat**: approximates "current
state" from the last historical snapshot per cell (no live streaming yet —
Phase 7); only time-of-day features are recomputed against the real clock.

Two real bugs caught and fixed while building this (see ADR-020 for detail):
an index/column mixup that broke every known-cell request, and a memory
allocation failure from a full-table sort, fixed by switching to `idxmax()`.

### Task 5 — Scenario simulator (PPT demo only)
`ml/notebooks/simulator.ipynb`. At threshold 45.0: 6,498/44,767 rows flagged
(14.5%) across only 25 of 1,423 distinct zones — a concentrated set of
hotspots drives most of the flagged volume. Threshold sweep + risk-level
view both included for presenter flexibility.

### Known limitations (Task 6, explicit requirement)
- **Cold-start geography** — confirmed by ADR-016; forecast service returns
  a conservative default for unseen cells rather than a fabricated number.
- **Missing enforcement timestamps** — `closed_datetime`/`action_taken_timestamp`
  100% missing (Phase 2); risk/recommendation engines never depend on them.
- **Internal-data-only constraint** (ADR-001) maintained throughout — no
  external data introduced for vehicle-mix or junction-history logic.
- `risk_score` weights/bands are a documented starting point, not validated
  against real intervention outcomes (none exist in the provided dataset).
