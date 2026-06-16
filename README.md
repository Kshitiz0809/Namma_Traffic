# Parking Intelligence + Predictive Alert Platform

Predicts **where** illegal parking violations are likely to occur, **when**
congestion is likely to begin, and **what** enforcement action to recommend —
built from real Bengaluru traffic-police violation records.

Built incrementally in 10 phases. This README is updated at the end of every
phase with what exists, how to run it, and what's next.

---

## Phase 1 — Project Setup + Data Ingestion ✅

### What was built
- Repo structure (backend/ml/frontend/infra/docs/submission separated by concern)
- Config layer (`backend/app/core/config.py`) — typed, validated settings loaded from `.env`
- Schema contract (`backend/app/ingestion/schema.py`) — the 24 expected dataset columns,
  required-non-null fields, and a Bengaluru lat/lon sanity range
- Ingestion module (`backend/app/ingestion/load_data.py`) — loads the raw CSV with
  correct dtypes/datetime parsing and validates it against the schema contract
- FastAPI app (`backend/app/main.py`) with `/` and `/health` (health check loads +
  validates the dataset so a broken file fails loudly, not silently)
- Docker Compose (`infra/docker-compose.yml`) — Postgres + Redis + backend
- Tests (`backend/tests/test_ingestion.py`) — real-data smoke test + 3 unit tests
  against deliberately broken sample data

### Files created
```
.
├── .env.example / .env
├── .gitignore
├── README.md
├── data/
│   ├── raw/violations_raw.csv        (298,450 rows, gitignored)
│   └── processed/                     (empty — populated in Phase 2)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py
│   │   ├── core/config.py
│   │   ├── ingestion/{schema.py, load_data.py}
│   │   ├── api/                       (empty — Phase 8)
│   │   └── schemas/                   (empty — Pydantic API models, Phase 8)
│   └── tests/test_ingestion.py
├── infra/docker-compose.yml
├── ml/{models, notebooks}             (empty — Phase 3+)
├── frontend/                          (empty — Phase 8)
├── docs/architecture/                 (empty — diagrams added as phases land)
└── submission/                        (empty — Phase 10)
```

### How to run

**Option A — local Python (recommended for fast iteration):**
```bash
cd backend
python -m venv ../.venv          # if not already created
../.venv/Scripts/activate        # Windows
pip install -r requirements.txt
python -m app.ingestion.load_data   # validate the dataset standalone
uvicorn app.main:app --reload --port 8000
# then: curl http://localhost:8000/health
```

**Option B — Docker Compose (Postgres + Redis + backend together):**
```bash
docker compose -f infra/docker-compose.yml up --build
```

### Test commands
```bash
cd backend
pytest -v
```

### Dataset contract (validated at ingestion)
24 columns: `id, latitude, longitude, location, vehicle_number, vehicle_type,
description, violation_type, offence_code, created_datetime, closed_datetime,
modified_datetime, device_id, created_by_id, center_code, police_station,
data_sent_to_scita, junction_name, action_taken_timestamp,
data_sent_to_scita_timestamp, updated_vehicle_number, updated_vehicle_type,
validation_status, validation_timestamp`

Required non-null: `id, latitude, longitude, created_datetime`.

### Known data quirks (discovered during ingestion, will matter in Phase 2)
- `violation_type` and `offence_code` are stringified JSON lists
  (e.g. `["WRONG PARKING","PARKING NEAR ROAD CROSSING"]`, `[112,104]`) — a single
  violation record can carry multiple offences. Needs explicit parsing, not a
  plain string compare.
- Missing values are encoded as the literal string `"NULL"`, not empty cells.
- `closed_datetime` / `action_taken_timestamp` are often null — many cases are
  still open or unresolved.

### Next risks
- **GeoPandas on Windows**: not yet installed (deferred to Phase 2, when we
  actually build spatial grids). GDAL wheels can be finicky on native Windows —
  if `pip install geopandas` fails, fallback is `conda install -c conda-forge geopandas`
  or use plain `numpy`/`shapely` grid binning instead of full GeoPandas.
- **Health check re-reads the full CSV** on every call — fine for a Phase 1
  smoke test, must switch to Postgres/parquet before any real traffic.
- Dataset has a Nov 2023 `created_datetime` in the sample row despite the
  filename saying "jan to may" — worth eyeballing the actual date range in
  Phase 2's temporal-trend visualization to make sure forecast windows
  (Phase 4) line up with reality.

---

## Phase 2 — Data Cleaning + Feature Engineering ✅

**Hard constraint honored throughout:** every feature uses only the 24
provided columns — no external data, maps, weather, or enrichment of any
kind (see `DECISIONS.md` ADR-001).

### What was built
- **`DECISIONS.md`** — 8 architecture decision records (H3 vs GeoHash, parquet,
  modular pipeline layout, target variable definition, leakage-safety pattern,
  outlier-flagging philosophy, modeling direction for Phase 3+)
- **Data audit** (`backend/app/ingestion/data_audit.py`) → `docs/data_quality_report.md`
  + `.json`: date range, monthly distribution, duplicate analysis, coordinate
  quality, validation_status breakdown — all against the real dataset
- **Modular feature pipeline** (`backend/app/features/`): `cleaning.py`,
  `outliers.py`, `spatial.py`, `temporal.py`, `operational.py`, `rolling.py`,
  `aggregated.py`, `targets.py`, orchestrated by `build_features.py`
- **H3-based spatial features** (resolution 9, ~174m hex) + GeoHash for
  comparison — both derived purely from lat/lon
- **Leakage-safe rolling/aggregated features** — every windowed or historical
  feature uses only data strictly before the current row (ADR-006), verified
  by brute-force unit tests, not just asserted in a docstring
- **Forward-looking targets** (`targets.parquet`, kept separate from
  `features.parquet` on purpose — ADR-005) for Phase 3 (`target_hotspot_60m`)
  and Phase 4 (`target_count_15m/30m/60m`)
- **`docs/feature_dictionary.md`** — every feature's formula, source columns,
  leakage risk, expected impact, and confirmation of internal-data-only use
- **Notebooks** (`ml/notebooks/`): `01_eda.ipynb` (volume/time/spatial/missingness
  charts), `02_feature_validation.ipynb` (independent re-check of leakage
  guarantees + correlation sanity check) — both executed with real outputs
  baked in, generated reproducibly from `_generate_notebooks.py`
- **`MODEL_REPORT.md`** skeleton — empty until Phase 3, structure in place

### Files created
```
DECISIONS.md
MODEL_REPORT.md
docs/data_quality_report.{md,json}
docs/feature_dictionary.md
backend/app/features/
  __init__.py, cleaning.py, outliers.py, spatial.py, temporal.py,
  operational.py, rolling.py, aggregated.py, targets.py, build_features.py
backend/app/models/__init__.py        (stub — Phase 3)
backend/app/serving/__init__.py       (stub — Phase 8)
backend/app/ingestion/data_audit.py
backend/tests/test_features.py
ml/requirements.txt
ml/notebooks/{01_eda.ipynb, 02_feature_validation.ipynb, _generate_notebooks.py}
data/processed/{features.parquet, targets.parquet}   (gitignored — regenerate locally)
```

### How to run
```bash
cd backend
pip install -r requirements.txt
python -m app.ingestion.data_audit          # -> docs/data_quality_report.{md,json}
python -m app.features.build_features       # -> data/processed/{features,targets}.parquet
pytest -v                                   # 12 tests, ~45s (includes full-dataset smoke test)
```
Notebooks:
```bash
pip install -r ../ml/requirements.txt
cd ../ml/notebooks
jupyter nbconvert --to notebook --execute --inplace 01_eda.ipynb
jupyter nbconvert --to notebook --execute --inplace 02_feature_validation.ipynb
```

### Test commands
```bash
cd backend && pytest -v
```
12/12 passing: 4 ingestion tests (Phase 1) + 8 feature tests, including
brute-force leakage-safety checks against synthetic data with known answers,
and a full-pipeline smoke test against the real 298,445-row dataset.

### Key real findings (not hypothetical — from the actual data)
- True date range: **2023-11-09 to 2024-04-08** (filename says "jan to may" — doesn't match)
- `closed_datetime` and `action_taken_timestamp` are **100% missing** → `resolution_time_minutes`
  is uncomputable in this extract; `enforcement_delay_minutes` falls back to
  `data_sent_to_scita_timestamp` (14.1% coverage); `validation_delay_minutes`
  uses `validation_timestamp` (58.0% coverage)
- 168 rows outside the Bengaluru bounding box (flagged via `is_outlier_coordinate`, not dropped)
- 9,521 rows share a (vehicle_number, created_datetime) pair (flagged via `is_duplicate_vehicle_event`, not dropped)
- 2,534 distinct H3 cells / 5,753 distinct GeoHash cells across the dataset
- Full pipeline (298,445 rows, 56 output columns) runs in **~25-28 seconds**

### Two real bugs caught by the leakage-safety tests (worth flagging honestly)
1. `rolling_hotspot_intensity` was initially implemented with `Series.ewm(times=...).mean()`
   on an all-1s indicator series — which is mathematically always 1.0 regardless
   of decay, so it carried zero signal. Replaced with a proper O(n) decayed-sum
   (Hawkes-process-style) recursion.
2. `violations_last_*m` and `target_count_*m` initially reassigned `groupby().rolling()`
   results back onto rows using **positional** index reattachment, which silently
   misaligned every group after the first when interleaved with other groups —
   same multiset of values, attached to the wrong rows. Caught by a brute-force
   unit test on synthetic data with hand-computed expected answers; aggregate
   stats (mean/std) looked identical before and after the fix, which is exactly
   why row-level tests mattered more than distribution sanity checks here.

### Next risks
- Time-based train/val/test split is required for Phase 3/4 (a random split
  would let leakage-safe-but-time-correlated rolling features still leak
  across the split boundary) — noted in `MODEL_REPORT.md`, not yet implemented.
- `resolution_time_minutes` being 100% empty means that spec'd feature
  contributes nothing in this dataset — flagged in `feature_dictionary.md`,
  worth rechecking if a fresher data extract becomes available.
- Outlier-coordinate and duplicate-vehicle-event rows are flagged but still
  included in `features.parquet` — Phase 3 must explicitly run with/without
  them and report the difference (ADR-007), not silently pick one.

---

## Phase 3 — Spatial Prediction Engine ✅

Primary objective reframed per review: **`target_hotspot_60m` binary
classification** is now the main model ("will this H3 area become a hotspot
in the next 60 minutes?"), with `target_count_60m` regression as a secondary
severity signal, and `congestion_score` computed as a derived/reported
metric only — not trained on directly this phase (DECISIONS.md ADR-011).

### What was built
- **5 new ADRs** (ADR-009 through ADR-013): live-availability exclusion of
  post-hoc admin columns, time-based split rationale, congestion-score
  definition, the 4 required ablation experiments, and the model feature set
- **`backend/app/models/`**: `split.py` (time-based train/val/test),
  `feature_set.py` (the live-prediction-safe feature list), `congestion_score.py`,
  `classifier.py` (CatBoost/LightGBM/XGBoost for the primary target),
  `regressor.py` (same 3 models for the secondary target), `explain.py` (SHAP),
  `experiments.py` (ablations A-D), `train.py` (orchestrator)
- **`docs/baseline_results.md`** — full model comparison, confusion matrix,
  calibration discussion, SHAP table, all 4 ablation experiments with honest
  caveats (e.g. Experiment C only swaps the categorical key, not the full
  spatial feature set)
- **`docs/leaderboard.csv`** — machine-readable results
- **`ml/notebooks/03_model_comparison.ipynb`** — confusion matrix heatmap,
  PR curve, calibration curve, SHAP summary plot, sample TP/FP/FN forecasts
- **6 saved models** in `ml/models/` (classifier + regressor × 3 libraries)
- **19/19 tests passing** (12 from Phase 1-2 + 7 new: split correctness,
  dtype casting, congestion-score bounds, metric sanity, a real-data smoke test)

### How to run
```bash
cd backend
pip install -r requirements.txt          # now includes catboost, lightgbm, xgboost, sklearn, shap
python -m app.models.train                # ~9 minutes — trains everything, runs experiments A-D
pytest -v                                 # 19 tests, ~75s
```
Notebook: `jupyter nbconvert --to notebook --execute --inplace ml/notebooks/03_model_comparison.ipynb`

### Real results (CatBoost won both objectives)
| Objective | Metric | Value |
|---|---|---|
| `target_hotspot_60m` (val) | PR-AUC | 0.8767 |
| `target_hotspot_60m` (test) | PR-AUC | 0.8732 |
| `target_count_60m` (val) | MAE / R² | 5.92 / 0.271 |

Full tables, confusion matrix, calibration, SHAP, and all 4 ablation results:
**`docs/baseline_results.md`**.

### Honest limitations (see `MODEL_REPORT.md` for details)
- Model is recall-leaning at its F1-optimal threshold (96.5% recall, 17.4%
  true-negative rate) — fine for "don't miss a hotspot," risky if read as
  "act on every positive prediction." Phase 6 must choose its own threshold.
- Calibration is moderate (Brier 0.1766), not exact.
- Experiment C isolates only the categorical spatial key, not a full
  H3-vs-GeoHash feature-set rebuild — flagged, not glossed over.

### Next risks
- `congestion_score` weights (0.5/0.3/0.2) are stated, not learned or
  validated against real outcomes — Phase 5 should treat it as a starting
  point, not ground truth.
- Duplicate-vehicle-event rows showed a small, consistent improvement when
  excluded (Experiment B) — not acted on yet, worth a closer look before Phase 4.

---

## Phase 3.5 — Decision Layer Hardening ✅ + Phase 4 — Multi-Horizon Forecast (initial) ✅

Goal: deployability/robustness, not a higher validation score (explicit
instruction — no model retraining for score-chasing). Five tasks, all run
against the real dataset, all results — including an honest FAIL — reported
as found.

### What was built
- **`backend/app/models/`**: `threshold_optimization.py` (cost-aware
  threshold sweep), `calibration.py` (Platt/Isotonic via sklearn's
  `FrozenEstimator`, ECE), `spatial_holdout.py` (H3-cell-level train/holdout
  split), `multi_horizon.py` (15/30/60/90m comparison + base-rate-corrected
  lift), `shap_audit.py` (bootstrap SHAP stability), `harden.py` (orchestrator)
- **`backend/app/features/targets.py`** extended: `target_hotspot_15m/30m/90m`
  added alongside the existing 60m target
- **5 new ADRs** (014-018) — cost model, test-set reuse policy, spatial
  holdout methodology+result, SHAP audit methodology+findings, multi-horizon
  base-rate caveat
- **11 generated artifacts** in `docs/`: `threshold_metrics.csv`,
  `threshold_selection.md`, `threshold_curve.png`, `calibration_results.csv`,
  `calibration_curve.png`, `spatial_holdout.md`, `region_performance.csv`,
  `horizon_comparison.csv`, `forecast_curves.png`, `feature_stability.csv`,
  `shap_summary.png`
- **`ml/notebooks/03_model_comparison.ipynb`** extended with 5 new sections
  covering all 5 tasks, re-executed with real outputs
- **12 new tests** (31/31 total passing)

### How to run
```bash
cd backend
python -m app.features.targets    # (only needed if rebuilding targets.parquet from scratch)
python -m app.models.harden        # ~5 minutes — runs all 5 hardening tasks
pytest -v                          # 31 tests, ~95s
```

### Results — including one explicit FAIL

| Task | Result | Decision |
|---|---|---|
| 1. Cost-aware threshold (FN 3x worse than FP) | Min-cost threshold = **0.15** (was 0.30) | **Switched default threshold** |
| 2. Calibration | Platt +0.66% / Isotonic +1.12% Brier improvement — both below the 5% bar | **Kept uncalibrated baseline** |
| 3. Spatial holdout (unseen H3 cells) | PR-AUC drop **7.88%** (bar was <5%) | **FAIL** — flagged, not hidden |
| 4. Multi-horizon (15/30/60/90m) | Raw PR-AUC rises with horizon (base-rate artifact); lift-corrected metric favors **shorter** horizons | Operational horizon stays **60m** (lead-time/consistency trade-off, documented) |
| 5. SHAP stability (5 bootstraps) | Top-10 perfectly stable (1.0); `h3_cell` mean rank 1.0 — corroborates Task 3 | Confirms spatial memorization is real |

**The headline finding:** Tasks 3 and 4 independently agree the model leans
on `h3_cell` identity more than is healthy for generalizing to brand-new
geographic coverage. This is surfaced as a documented limitation (see
`docs/spatial_holdout.md` for redesign recommendations) rather than hidden
or silently patched — the instruction was to prioritize deployability and
honesty over a better-looking metric, and this is exactly the kind of result
that instruction was meant to surface.

Full writeup: **`docs/baseline_results.md`** ("Phase 3.5/4" section) and
**`MODEL_REPORT.md`**.

### Next risks
- Spatial generalization FAIL is not fixed yet — Phase 5/6 deployment should
  assume the model is reliable on already-seen H3 cells only, until a
  feature redesign (or retraining on expanded coverage) is done.
- The 3:1 false-negative-to-false-positive cost ratio (Task 1) is a stated
  assumption, not measured — replace with real intervention-cost data if it
  becomes available.
- Multi-horizon targets (15/30/90m) exist in `targets.parquet` but only got
  a single baseline comparison run — not the full ablation/calibration
  treatment the 60m target received.

### Final robustness check — Reduced-Spatial-Identity Experiment ✅ (feature set now FROZEN)

One last experiment before lock, per explicit instruction (single
comparison, no architecture changes, no extra variants): does the model
still work without `h3_cell`/`geohash` themselves? Model A = existing
winner (not retrained). Model B = one new run with `h3_cell`/`geohash`
removed, everything else (density, rolling, temporal, historical-risk,
organizational categoricals) kept.

**Result: PR-AUC drop of only 0.55% (0.8767 → 0.8719) → Spatial abstraction
= PASS.** This does NOT contradict the spatial-holdout FAIL above — that
measures cold-start failure on cells with zero history of any kind; this
measures `h3_cell`'s marginal value for cells the model already has data
on, which is small because other features already capture similar
information. Full reasoning: `docs/spatial_dependency.md`. **Decision: keep
`h3_cell`** (negligible robustness gain from removing it, for a real
accuracy cost) — **feature set is now frozen** for Phase 5+.

---

## Phase 5 — Parking-Induced Congestion Risk Engine ✅

**Renamed from "Congestion Impact Engine"** per review: the system estimates
operational risk derived from parking violation behavior, not measured
traffic congestion. Feature set remains frozen (Phase 4 lock) — no
retraining this phase, only derived scoring/rules/serving on top of the
existing frozen models.

### What was built
- **`backend/app/models/risk_score.py`** — `risk_score` (0-100), a derived
  score (NOT a new ML target) from the frozen classifier + regressor outputs
  plus `rolling_hotspot_intensity`/`violations_last_15m`. Data-driven band
  cutoffs (34.0/45.1/54.2) — fixed 40/60/80 was tried first and rejected for
  leaving CRITICAL empty. Full derivation: `docs/risk_definition.md`.
- **`backend/app/models/recommendation.py`** + **`docs/recommendation_rules.yaml`**
  — rule-based (no LLM) Monitor/Patrol/Deploy enforcement/Tow operation
  candidate, with vehicle-mix + junction-history escalation rules.
- **`backend/app/models/alerts.py`** → **`docs/alerts.json`** — GREEN/YELLOW/
  ORANGE/RED alerts with zone, probability, risk, and top contributing factors.
- **`backend/app/serving/forecast_service.py`** — `GET /forecast`, wired into
  the FastAPI app, tested via `TestClient` across 4 scenarios.
- **`ml/notebooks/simulator.ipynb`** — threshold/risk-level scenario explorer
  (PPT demo only, explicit scope).
- **ADR-020** (DECISIONS.md) — full Phase 5 design rationale.

### How to run
```bash
cd backend
pip install -r requirements.txt              # adds pyyaml
python -m app.models.generate_phase5_artifacts  # -> docs/alerts.json + distributions
uvicorn app.main:app --reload --port 8000
# curl "http://localhost:8000/forecast?h3_cell=89618925c03ffff"
```

### Real results
- **Risk distribution** (validation set, 44,767 rows): LOW 58.1%, MEDIUM
  27.6%, HIGH 11.9%, CRITICAL 2.4%.
- **Recommendations**: Monitor 26,013, Patrol 12,281, Deploy enforcement
  5,373, Tow operation candidate 1,100. 64 escalations triggered by the
  vehicle-mix/junction-history rules.
- **Alerts**: 60 representative alerts generated (20 per non-LOW level).
- **API**: `/forecast?h3_cell=89618925c03ffff` → hotspot_probability 0.625,
  predicted_count 7.6, congestion_risk 27.92, risk_band LOW, recommendation
  Monitor, confidence 0.251. Vehicle-type override (e.g. to a heavy/commercial
  type) correctly raises the probability and confidence.
- **Simulator**: at threshold 45.0, only 25 of 1,423 distinct zones account
  for 6,498 of 44,767 flagged rows — a small set of hotspots drives most volume.

### A real data quirk found and worked around
`junction_name == "No Junction"` is ~49.5% of all rows — a placeholder, not
a real location — which inflates that category's historical-risk share to
~0.5 (looks like "the most concentrated junction" but isn't a real signal).
The escalation rule explicitly excludes it and calibrates its threshold
against named-junctions-only statistics (median 0.013, not ~0.5).

### Two real bugs caught while building the forecast service
1. `.set_index("h3_cell")` silently dropped `h3_cell` from the row's own
   columns, breaking every known-cell request — fixed by restoring it after lookup.
2. A full `sort_values()` on the 298k-row features table hit a memory
   allocation failure in one execution context — replaced with `idxmax()`
   (one pass, no full-table sort).

### Known limitations (explicit Task 6 requirement)
- **Cold-start geography** — confirmed by Phase 3.5's spatial holdout FAIL;
  the forecast service returns a conservative default for unseen cells.
- **Missing enforcement timestamps** — `closed_datetime`/`action_taken_timestamp`
  are 100% missing (Phase 2 finding); the risk/recommendation engines never
  depend on them.
- **Internal-data-only constraint** maintained — no external data introduced
  for vehicle-mix classification or junction-history logic.
- `risk_score` weights and band cutoffs are a documented starting point, not
  validated against real intervention outcomes (none exist in this dataset).

---

## Phases 6–10
Not started yet. See the build prompt for full scope; each phase gets its own
README section, architecture diagram update, and approval checkpoint before
the next phase begins.
