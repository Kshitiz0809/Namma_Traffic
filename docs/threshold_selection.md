# Threshold Selection — Phase 3.5 Task 1

Cost model: `cost = FP * 1 + FN * 3` (missing a real hotspot assumed 3x worse than a wasted patrol — a stated assumption, see DECISIONS.md ADR-014).

Full sweep (0.05-0.95, step 0.05): `threshold_metrics.csv`, `threshold_curve.png`.

## Recommended operating points

### f1_threshold
- Threshold: **0.3**
- Precision: 0.7316, Recall: 0.9620, F1: 0.8311
- Cost: 14624
- Rationale: Maximizes F1 — Phase 3's original criterion, kept here for comparison.

### high_precision_threshold
- Threshold: **0.7**
- Precision: 0.8536, Recall: 0.6352, F1: 0.7284
- Cost: 37687
- Rationale: Lowest-cost threshold among those with precision >= 0.85 — for patrol-capacity-constrained deployments.

### balanced_threshold
- Threshold: **0.15**
- Precision: 0.7053, Recall: 0.9959, F1: 0.8258
- Cost: 13415
- Rationale: Minimizes total intervention cost (FP*1.0 + FN*3.0) — the new recommended default.

**Default recommendation: `balanced_threshold`** — it directly optimizes the stated cost model rather than a proxy metric, and the cost model is the actual decision-relevant quantity for an alert system.