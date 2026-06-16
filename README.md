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

## Phases 2–10
Not started yet. See the build prompt for full scope; each phase gets its own
README section, architecture diagram update, and approval checkpoint before
the next phase begins.
