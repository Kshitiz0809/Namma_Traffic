# Risk Definition — Parking-Induced Congestion Risk Engine

Phase 5 Task 1. This is a **derived score, not a new ML target** (explicit
instruction) — computed from the model outputs
(`ml/models/classifier_catboost.cbm`, `ml/models/regressor_catboost.cbm`)
plus existing leakage-safe features. Code: `backend/app/models/risk_score.py`.

**Phase 8 update (DECISIONS.md ADR-023):** the weights below were
originally hand-picked. They are now FIT — via ridge-regularized
non-negativity-constrained regression (NNLS) against `target_count_60m`
(the closest available outcome proxy; there is still no ground-truth
congestion/enforcement data in the provided dataset) — and refit
automatically on every retrain. The formula shape is unchanged; only the
weight values are now data-driven, persisted in `ml/models/risk_params.json`
instead of hardcoded as a module constant.

## Formula

```
risk_score = 100 * (
    w_hotspot  * hotspot_probability
  + w_count    * normalized_predicted_count
  + w_persist  * persistence
  + w_recent   * recent_intensity
)
```

Current fitted weights (from the latest retrain — see `ml/models/risk_params.json`):
`{hotspot_probability: 0.023, normalized_predicted_count: 0.701, persistence: 0.145, recent_intensity: 0.131}`.
The original hand-picked starting point was `0.40 / 0.30 / 0.20 / 0.10` in
the same component order — kept below for historical reference only.

Scale: **0-100**, higher = higher operational risk.

## Component definitions

| Component | Source | Definition |
|---|---|---|
| `hotspot_probability` | Frozen CatBoost **classifier** (`target_hotspot_60m`) | `predict_proba()[:, 1]` — already 0-1, no scaling needed |
| `normalized_predicted_count` | Frozen CatBoost **regressor** (`target_count_60m`) | Raw prediction min-max scaled to 0-1 |
| `persistence` | `rolling_hotspot_intensity` (Phase 2 feature, leakage-safe Hawkes-decay) | Min-max scaled to 0-1 — "how sustained has activity been in this cell" |
| `recent_intensity` | `violations_last_15m` (Phase 2 feature) | Min-max scaled to 0-1 — "what just happened, right now" |

## Why these specific weights — original rationale (superseded, Phase 8)

The original `0.40 / 0.30 / 0.20 / 0.10` weights were a direct, explicit
instruction, not a learned/optimized weighting: the model's own probability
output got the largest share, followed by predicted severity, persistence,
then recent spike. **Phase 8 (ADR-023) replaced this with a fitted weight
set** (see above) once a retraining pipeline existed to refit it against
`target_count_60m` on every retrain — a plain NNLS fit first collapsed to
100% weight on `normalized_predicted_count` alone (the regressor is
literally trained to predict that same target, so this is near-tautological,
not genuine signal diversity), which `fit_risk_weights`'s ridge
regularization corrects by enforcing that no single component exceeds 75%
of total weight.

## Normalization (leakage-safe, ADR-011 discipline)

`normalized_predicted_count`, `persistence`, and `recent_intensity` are all
min-max scaled using statistics fit on the **train period only**
(2023-11-09 → 2024-02-19), then applied (and clipped, not extrapolated) to
val/test/future rows — exactly the same discipline as `congestion_score.py`.
`hotspot_probability` needs no scaling; it's already a probability.

Fitted train-period ranges (from `RiskMinMaxParams`):
- `predicted_count`: -3.70 to 114.81 (regressor predictions can go slightly
  negative since nothing constrains them — clipped to 0 at the scaling step)
- `rolling_hotspot_intensity`: 0.0 to 370.35
- `violations_last_15m`: 0.0 to 114.0

## Risk bands — DATA-DRIVEN, not arbitrary round numbers

**First attempt used fixed cutoffs (40/60/80)** and left the CRITICAL band
essentially empty — the real score distribution tops out around 65-82, not
100, because the 4 weighted components rarely all peak simultaneously
(e.g. a cell can have very high `hotspot_probability` while its
`recent_intensity` is still low if the burst just started). **Replaced with
percentile cutoffs from the train-period distribution**:

| Band | Score range | ~Train percentile | Train population | Validation population |
|---|---|---|---|---|
| LOW | 0 - 34.0 | 0-50th | 50.0% | 58.1% |
| MEDIUM | 34.0 - 45.1 | 50th-85th | 35.0% | 27.6% |
| HIGH | 45.1 - 54.2 | 85th-97th | 12.0% | 11.9% |
| CRITICAL | 54.2+ | 97th-100th | 3.0% | 2.4% |

Validation-period populations are close to train (58/28/12/2% vs. 50/35/12/3%)
— the bands transfer reasonably to held-out time, not just memorized from train.

## Interpretation

- **LOW**: business-as-usual. No elevated signal across any component.
- **MEDIUM**: at least one component elevated (commonly `hotspot_probability`
  alone) but not a sustained or currently-active pattern.
- **HIGH**: multiple components elevated together — model is confident AND
  there's supporting recent/persistent activity.
- **CRITICAL**: top ~3% — high confidence, high predicted severity, and
  recent/sustained activity all align. This is the population the
  recommendation engine (Task 2) maps toward "tow operation candidate."

## Known limitation

These weights and band cutoffs are **not validated against real
intervention outcomes** (no ground truth exists for "was this risk score
useful" in the provided dataset) — they're a documented, reproducible
starting point. Phase 6+ should recalibrate if/when outcome data becomes available.
