# Phase 3 — Baseline Results

All numbers below are from a single real run of `backend/app/models/train.py`
against the actual 298,445-row dataset (verified twice for consistency —
see commit history). Raw machine-readable results: `docs/leaderboard.csv`.

---

## Objectives (per user's Phase 3 scope adjustment)

1. **PRIMARY — `target_hotspot_60m`** (binary classification): *"Will this
   H3 area become a hotspot in the next 60 minutes?"*
2. **SECONDARY — `target_count_60m`** (regression): *"How severe will
   hotspot activity become?"*
3. **`congestion_score`** — derived/reported only (see below), NOT trained
   on directly this phase (DECISIONS.md ADR-011).

## Split (DECISIONS.md ADR-010 — time-based, not random)

| Split | Date range | Rows |
|---|---|---|
| Train | 2023-11-09 19:11 → 2024-02-19 21:31 | 208,911 |
| Validation | 2024-02-19 21:34 → 2024-03-14 20:07 | 44,767 |
| Test | 2024-03-14 20:08 → 2024-04-08 17:30 | 44,767 |

Model selection (picking the winner) happens on **validation** only. **Test
is touched exactly once**, with the already-chosen winner, at the end.

---

## 1. Primary objective — `target_hotspot_60m` classification

| Model | PR-AUC | Precision | Recall | F1 | Brier Score | Threshold |
|---|---|---|---|---|---|---|
| **CatBoost** | **0.8767** | 0.7316 | 0.9620 | **0.8311** | **0.1766** | 0.30 |
| LightGBM | 0.8649 | 0.7351 | 0.9505 | 0.8290 | 0.1832 | 0.30 |
| XGBoost | 0.8632 | 0.7245 | 0.9567 | 0.8246 | 0.1918 | 0.20 |

**Winner: CatBoost** (highest PR-AUC and F1, lowest Brier score = best
calibration of the three). Native categorical handling for `h3_cell`
(2,534 categories), `junction_name`, `police_station`, `vehicle_type`,
`primary_offence_code`, `primary_violation_type`, `center_code` likely
contributes — these are exactly the columns CatBoost handles without
manual encoding (DECISIONS.md ADR-008's stated hypothesis for trying it first).

Threshold per model is the value (searched over 0.05-0.95) that maximizes
F1 on validation — not a fixed 0.5, since the positive class is the majority
(~70%) and a default cutoff would not reflect a sensible decision boundary
for this imbalance.

### Test set (CatBoost, threshold fixed at the validation-chosen 0.30)

| Metric | Value |
|---|---|
| PR-AUC | 0.8732 |
| Precision | 0.7341 |
| Recall | 0.9651 |
| F1 | 0.8339 |
| Brier Score | 0.1766 |
| Positive rate (test) | 0.7027 |

Test metrics track validation closely (PR-AUC 0.8732 vs 0.8767) — no sign of
overfitting to the validation period.

### Confusion matrix (test, threshold 0.30)

| | Predicted: Not Hotspot | Predicted: Hotspot |
|---|---|---|
| **Actual: Not Hotspot** | 2,310 (TN) | 10,999 (FP) |
| **Actual: Hotspot** | 1,098 (FN) | 30,360 (TP) |

**Honest read of this matrix:** the model strongly favors recall over
specificity at this threshold — it catches 96.5% of real hotspot events
(low false-negative rate, good for an alert system that shouldn't miss
incidents) but flags a lot of non-hotspots as hotspots too (only 17.4% true
negative rate: 2,310 / 13,309). This is the F1-optimal point, but Phase 6's
alert engine should NOT treat "predicted hotspot" as "act immediately" —
the FP rate here means roughly 4 in 5 negative cases get a positive
prediction. A higher threshold trades recall for precision; which trade-off
is right depends on the cost of a missed hotspot vs. a wasted patrol, a
decision for Phase 6, not baked in here.

### Calibration

Brier score 0.1766 (CatBoost) — see `ml/notebooks/03_model_comparison.ipynb`
for the visual reliability curve. A Brier score of 0 is perfect; 0.25 is the
score of a model that always predicts 0.5. 0.1766 indicates moderate but
imperfect calibration — predicted probabilities are directionally
meaningful but shouldn't be read as exact percentages without a
calibration layer (e.g. isotonic regression), which is not implemented
this phase.

### SHAP — top 10 features (CatBoost, validation sample of 2,000 rows)

| Rank | Feature | Mean \|SHAP\| |
|---|---|---|
| 1 | `h3_cell` | 0.435 |
| 2 | `rolling_hotspot_intensity` | 0.240 |
| 3 | `vehicle_type` | 0.136 |
| 4 | `violations_last_15m` | 0.099 |
| 5 | `hour_cos` | 0.088 |
| 6 | `primary_offence_code` | 0.081 |
| 7 | `violations_last_60m` | 0.060 |
| 8 | `primary_violation_type` | 0.047 |
| 9 | `center_code` | 0.044 |
| 10 | `violation_density` | 0.041 |

**Read:** location (`h3_cell`) dominates, as expected for a spatial hotspot
problem — but the next-strongest signal is `rolling_hotspot_intensity`, a
Phase 2 engineered feature (the Hawkes-decay intensity, not a raw count),
which validates that the more sophisticated rolling features earn their
complexity (also confirmed directly in Experiment D below). See
`ml/notebooks/03_model_comparison.ipynb` for the SHAP summary plot.

---

## 2. Secondary objective — `target_count_60m` regression

| Model | MAE | RMSE | R² |
|---|---|---|---|
| **CatBoost** | **5.92** | **10.58** | **0.271** |
| LightGBM | 6.02 | 10.92 | 0.223 |
| XGBoost | 6.24 | 11.18 | 0.186 |

**Winner: CatBoost** again. R² of 0.27 means the model explains ~27% of the
variance in "how many violations will happen in this cell in the next hour"
— a real but modest signal; count regression on a sparse, highly variable
event process is intrinsically harder than the binary hotspot/not-hotspot
framing. This is reported honestly rather than oversold — Phase 4's
forecast engine should treat this as a baseline to beat, not a finished result.

---

## 3. Congestion score (derived, NOT trained — DECISIONS.md ADR-011)

```
congestion_score = 0.5 × normalized_violation_count   (from violation_density)
                  + 0.3 × hotspot_persistence          (from rolling_hotspot_intensity)
                  + 0.2 × enforcement_density           (from police_station_density)
```
All three components min-max scaled using statistics fit on the **train
period only** (rows up to 2024-02-19), then applied to the full dataset.

| Statistic | Value |
|---|---|
| Mean | 0.096 |
| Std | 0.048 |
| Min | 0.000 |
| 25th pct | 0.057 |
| Median | 0.086 |
| 75th pct | 0.117 |
| Max | 0.565 |

Right-skewed, as expected — most cell/time contexts are not severely
congested; a smaller number of cells drive the high end. Saved to
`data/processed/congestion_score.parquet` (id, h3_cell, created_datetime,
the 3 normalized components, and the final score) for Phase 5 to consume.

---

## 4. Required ablation experiments (DECISIONS.md ADR-012)

All run with CatBoost (the chosen baseline), same validation split, PR-AUC
as the primary comparison metric.

### A. With vs without `is_outlier_coordinate` rows (168 rows)

| Variant | PR-AUC | F1 | n |
|---|---|---|---|
| With outliers | 0.8767 | 0.8311 | 44,767 |
| Without outliers | 0.8743 | 0.8303 | 44,742 |

**Finding:** negligible difference (ΔPR-AUC = 0.0024). The 168 flagged rows
are too small a fraction of 298k to meaningfully move aggregate metrics
either way. **Decision: keep outliers in** (no evidence they hurt, and
removing real-but-unusual data by default isn't justified by this result).

### B. With vs without `is_duplicate_vehicle_event` rows (9,521 rows)

| Variant | PR-AUC | F1 | n |
|---|---|---|---|
| With duplicates | 0.8767 | 0.8311 | 44,767 |
| Without duplicates | 0.8772 | 0.8330 | 43,339 |

**Finding:** removing duplicate-vehicle-event rows gives a marginal
improvement (ΔPR-AUC = +0.0005, ΔF1 = +0.0019) — small but consistently in
the "better without" direction across both metrics. **Decision: worth
revisiting in Phase 4+ if duplicates turn out to be a logging artifact
rather than genuine simultaneous violations** — the effect is real but small
enough that it's not yet justified as a default data-cleaning rule.

### C. H3 vs GeoHash as the spatial categorical key

| Variant | PR-AUC | F1 | n |
|---|---|---|---|
| H3 cell | 0.8767 | 0.8311 | 44,767 |
| GeoHash | 0.8759 | 0.8309 | 44,767 |

**Finding:** H3 is marginally better (ΔPR-AUC = 0.0008), consistent with
but not strongly confirming the ADR-002 hypothesis (equal-area hexagons >
latitude-distorted rectangles). **Caveat:** this experiment swaps only the
*categorical identity column* the model sees — the numeric density/rolling
features (`hotspot_frequency`, `violation_density`, `junction_density`,
`police_station_density`) remain H3-cell-derived in both arms (recomputing
the entire feature set on a GeoHash grid was out of scope for this
ablation). So this isolates "which spatial ID does the model see," not the
full grid-design choice — a fully clean H3-vs-GeoHash comparison would
re-derive every spatial feature on each grid, which is a larger undertaking
flagged here rather than silently skipped.

### D. Raw counts only vs full rolling feature set

| Variant | PR-AUC | F1 | n |
|---|---|---|---|
| Raw counts only (`hotspot_frequency` alone) | 0.8701 | 0.8256 | 44,767 |
| Full rolling set (`violations_last_15/30/60m`, `same_hour_previous_day`, `rolling_hotspot_intensity`) | 0.8767 | 0.8311 | 44,767 |

**Finding:** the clearest result of the four experiments. Adding the
rolling/windowed features improves PR-AUC by 0.0066 and F1 by 0.0055 —
small in absolute terms but the largest, most consistent gap of any
experiment here, and it agrees with the SHAP ranking (`rolling_hotspot_intensity`
is the #2 feature overall). **Decision: keep the full rolling feature set** —
this is the one experiment with a real, attributable effect size, validating
the extra engineering effort from Phase 2.

---

## Summary of decisions made from these experiments
- Keep outlier-coordinate rows in (Experiment A: no measurable harm).
- Keep duplicate-vehicle-event rows in for now, flag for revisit (Experiment B: small but real improvement without them).
- Keep H3 as primary spatial key (Experiment C: ADR-002's rationale holds, modestly).
- Keep the full rolling feature set — it's the one feature-engineering choice with a clearly attributable effect (Experiment D).

---

# Phase 3.5 / 4 — Decision Layer Hardening + Forecast Readiness

Goal of this round: deployability and robustness, NOT chasing higher
validation PR-AUC (explicit instruction). Full artifacts: `threshold_metrics.csv`,
`threshold_selection.md`, `threshold_curve.png`, `calibration_results.csv`,
`calibration_curve.png`, `spatial_holdout.md`, `region_performance.csv`,
`horizon_comparison.csv`, `forecast_curves.png`, `feature_stability.csv`,
`shap_summary.png` — all in `docs/`, all generated by
`backend/app/models/harden.py` against the real dataset.

## Task 1 — Cost-aware threshold selection (DECISIONS.md ADR-014)

Cost model: `cost = FP×1 + FN×3` (a missed hotspot assumed 3x worse than a
wasted patrol — stated assumption, not measured).

| Operating point | Threshold | Precision | Recall | F1 | Cost |
|---|---|---|---|---|---|
| F1-optimal (Phase 3 default) | 0.30 | 0.7316 | 0.9620 | 0.8311 | 14,624 |
| High-precision (≥0.85 precision) | 0.70 | 0.8536 | 0.6352 | 0.7284 | 37,687 |
| **Balanced (min-cost) — new default** | **0.15** | 0.7053 | 0.9959 | 0.8258 | **13,415** |

**Recommendation: switch the default operating threshold from 0.30 to 0.15.**
At 0.15, recall rises to 99.6% (almost no missed hotspots) at a real but
acceptable precision cost (70.5%), and total cost drops by ~8% vs. the
F1-optimal threshold. This is a direct consequence of weighting false
negatives 3x — the F1 criterion never "knew" about that asymmetry.

## Task 2 — Probability calibration (DECISIONS.md ADR-015)

| Method | Brier | Brier improvement | ECE | PR-AUC | PR-AUC delta |
|---|---|---|---|---|---|
| Baseline (uncalibrated) | 0.1766 | — | 0.0321 | 0.8732 | — |
| Platt (sigmoid) | 0.1755 | +0.66% | 0.0256 | 0.8732 | 0.00% |
| Isotonic | 0.1747 | +1.12% | 0.0083 | 0.8692 | -0.47% |

**Decision: keep baseline (uncalibrated).** Neither method clears the ≥5%
Brier-improvement bar required to justify the added complexity, even though
isotonic does measurably improve ECE (0.0321→0.0083). If Phase 6 needs
better-calibrated probabilities specifically (not just rank-ordering),
isotonic is the better of the two — but it doesn't meet this phase's
acceptance threshold, so it isn't adopted by default.

## Task 3 — Spatial generalization test (DECISIONS.md ADR-016) — ⚠️ FAIL

| Region set | PR-AUC | Precision | Recall | Rows |
|---|---|---|---|---|
| Seen (train-cells) | 0.8833 | 0.7399 | 0.9626 | 37,032 |
| Unseen (holdout-cells) | 0.8137 | 0.6906 | 0.9640 | 7,289 |

**PR-AUC drop: 7.88%** (threshold for PASS was <5%). **Verdict: FAIL —
feature redesign recommended.**

This is the most important finding of this hardening round. It's
corroborated independently by Task 5's SHAP audit (`h3_cell` is the #1
feature with mean rank 1.0 across every bootstrap, never displaced). The
model works well on cells it has seen before — which is most of its
realistic deployment scope, since Bengaluru's H3 grid is fixed — but should
NOT be trusted to generalize to genuinely new geographic coverage without
retraining. Full discussion + redesign recommendations: `docs/spatial_holdout.md`.

## Task 4 — Multi-horizon comparison (DECISIONS.md ADR-018)

| Horizon | PR-AUC (raw) | Positive rate | Lift over base rate |
|---|---|---|---|
| 15m | 0.7834 | 60.5% | **1.294** |
| 30m | 0.8337 | 65.3% | 1.276 |
| 60m | 0.8767 | 70.0% | 1.253 |
| 90m | 0.8929 | 72.4% | 1.234 |

**Critical caveat:** raw PR-AUC rises with horizon almost entirely because
longer windows have a higher positive rate — not because longer-horizon
predictions are inherently more skillful. `lift_over_base_rate` (PR-AUC ÷
positive rate) corrects for this, and **by that corrected measure, shorter
horizons are actually relatively more informative** (15m: 1.294 vs 90m: 1.234)
— the opposite conclusion from reading raw PR-AUC alone.

**Recommendation: 60m remains the recommended operational horizon**, balancing:
- Strong absolute performance (PR-AUC 0.8767, only modestly below 90m's 0.8929)
- Reasonable lift (1.253, close to the 15m maximum of 1.294 — not the worst trade)
- Practical lead time for an enforcement response (15-30m may be too short
  to dispatch a patrol; 90m's lift is the weakest of the four)
- Consistency with `congestion_score` and all Phase 3 artifacts already
  built around the 60m window — switching now would invalidate completed
  work without a strong enough signal to justify it

15m is the better choice ONLY if the deployment context specifically values
relative predictive skill over absolute confidence and short reaction time
— a Phase 6 deployment decision, not assumed here.

## Task 5 — Explainability audit (DECISIONS.md ADR-017)

- **Stability: PASS.** Top-10 SHAP features are perfectly stable across 5
  bootstrap resamples (Jaccard score 1.0 — same 10 features every time).
- **H3 dominance: confirmed.** `h3_cell` mean rank 1.0 across all bootstraps
  (always #1). Corroborates Task 3's spatial holdout failure independently.
- **Timestamp leakage: none detected.** No raw timestamp column is in the
  model feature set (verified programmatically, not just by inspection).
- **Target proxies: none detected.** No numeric feature exceeds 0.95
  correlation with the target (strongest engineered features sit around 0.3-0.4).

Full table: `feature_stability.csv`. Plot: `shap_summary.png`.

## Final recommendation going into Phase 5

| Decision | Value |
|---|---|
| Operating threshold | **0.15** (balanced/min-cost, not the old F1-optimal 0.30) |
| Calibration | None applied — baseline probabilities are used as-is |
| Operational horizon | **60 minutes** (`target_hotspot_60m`), unchanged from Phase 3 |
| Spatial robustness | **FAIL** — flagged as a known limitation, not silently accepted |
| Known limitations | (1) model partially memorizes `h3_cell` identity — won't generalize to new geographic coverage without retraining; (2) probabilities are only moderately calibrated (Brier 0.1766, ECE 0.032); (3) raw PR-AUC is not comparable across forecast horizons due to base-rate differences — always read `lift_over_base_rate` alongside it |
