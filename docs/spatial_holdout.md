# Spatial Generalization Test — Phase 3.5 Task 3

Split 1824 H3 cells into train-cells, 455 into holdout-cells (80/20, random, seed=42). Retrained CatBoost on train-period rows restricted to train-cells, then evaluated on the SAME validation time window split by whether the row's cell was seen during training.

- Seen-region PR-AUC: **0.8833** (37,032 rows)
- Unseen-region PR-AUC: **0.8137** (7,289 rows)
- PR-AUC drop: **7.88%**
- Verdict: **FAIL — recommend feature redesign**

## Honest interpretation
PR-AUC drops by 7.88% on H3 cells never seen during training — above the 5% acceptance threshold. This is consistent with the SHAP audit (`feature_stability.csv`), which found `h3_cell` is the single dominant feature (mean rank 1.0 across bootstraps). **The model partially memorizes per-cell identity rather than purely generalizing from cell-agnostic signals (time-of-day, vehicle type, rolling intensity).** This does not make the model useless — most real deployments would see cells that DID appear in training data, since Bengaluru's H3 grid is fixed and largely covered by the training period — but it does mean **the model should not be trusted to generalize to genuinely new geographic areas** (e.g. if the city's enforcement coverage expands to new zones) without retraining on data from those zones first.

## Recommendation
Feature redesign candidates for Phase 4, in order of expected leverage:
1. Add cell-agnostic spatial covariates (e.g. road density proxies — though ADR-001 forbids external data, internally-derivable proxies like junction_density are already present and under-weighted relative to h3_cell itself).
2. Consider regularizing or capping h3_cell's influence (e.g. via CatBoost's `max_ctr_complexity` or explicit feature weighting) to force more reliance on generalizable signals — at a likely cost to in-distribution accuracy, a deliberate trade Phase 4 should evaluate, not assume.