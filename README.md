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

## Phases 3–10
Not started yet. See the build prompt for full scope; each phase gets its own
README section, architecture diagram update, and approval checkpoint before
the next phase begins.
