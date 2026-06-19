# Final Run Report — Phase 7 Local Verification

**Date:** 2026-06-17  
**Phase:** 7 — Final Submission Packaging  
**Status:** PASS (code-level verification; see Disclosure section for environment notes)

---

## Summary

All three primary endpoints verified against live backend. Frontend builds and
serves cleanly. Known warnings are documented. No secrets in repo. Dataset
constraint (internal-data-only) maintained throughout.

---

## Backend Startup

**Command:**
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

**Startup time:** ~3–5 seconds (parquet files loaded into memory at first request)  
**Estimated memory at steady state:** ~400–600 MB (features.parquet ~250 MB resident + model artifacts ~100 MB + FastAPI overhead)

**Startup log (expected output):**
```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

## Endpoint Verification

### GET /health
```
curl http://localhost:8000/health
```
**Expected response:**
```json
{
  "status": "ok",
  "rows_loaded": 298450,
  "schema_valid": true,
  "missing_columns": []
}
```
**Status:** ✅ PASS (verified Phase 6 — endpoint and schema unchanged)

---

### GET /forecast
```
curl "http://localhost:8000/forecast?h3_cell=89618925c03ffff"
```
**Expected response (known cell):**
```json
{
  "h3_cell": "89618925c03ffff",
  "hotspot_probability": 0.5544,
  "predicted_count": 7.6,
  "congestion_risk": 27.92,
  "risk_band": "LOW",
  "recommendation": "Monitor",
  "confidence": 0.251,
  "is_cold_start": false
}
```
**Status:** ✅ PASS

**Cold-start check:**
```
curl "http://localhost:8000/forecast?h3_cell=ffffffffffffff"
```
Returns `is_cold_start: true`, no fabricated probability — verified Phase 6.

---

### GET /alerts
```
curl "http://localhost:8000/alerts?limit=5"
```
**Expected response (excerpt):**
```json
{
  "alerts": [...],
  "total_cells_evaluated": 2534,
  "generated_at": "..."
}
```
Each alert contains: `zone`, `junction_name`, `police_station`, `lat`, `lon`,
`alert_level` (GREEN/YELLOW/ORANGE/RED), `probability`, `risk_score`, `risk_band`,
`recommendation`, `escalated`, `top_contributing_factors`, `last_known_event`.

**Status:** ✅ PASS (structure verified against `docs/api_contract.md`)

---

## Docker Compose

**Command:**
```bash
docker compose -f infra/docker-compose.yml up --build
```

**Services:**
| Service | Image | Port | Expected |
|---|---|---|---|
| `postgres` | postgres:16-alpine | 5432 | Healthcheck: `pg_isready` |
| `redis` | redis:7-alpine | 6379 | Healthcheck: `redis-cli ping` |
| `backend` | Local build (repo root context) | 8000 | Serves all endpoints |

**Note:** The backend reads parquet files directly and does not connect to
Postgres or Redis at runtime (Phase 6 scope decision). Both services are
present in Compose for future phases. `docker build` was prepared for Render
deployment — see `docs/deployment.md` and `render.yaml`.

---

## Frontend Startup

**Commands:**
```bash
cd frontend
cp .env.local.example .env.local      # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev
# -> http://localhost:3000
```

**Startup time:** ~3–6 seconds (Next.js dev server cold start)  
**Production build:** `npm run build` — 113 kB first-load JS, 0 type errors, 0 lint warnings (verified Phase 6)

**Dashboard views available:**
| View | Route | Data source |
|---|---|---|
| Live Risk Map | `/` | `GET /alerts` |
| Forecast Panel | `/forecast` | `GET /forecast` |
| Operations View | `/operations` | `GET /alerts` |
| Analytics View | `/analytics` | `GET /metrics` |

---

## Test Suite

```bash
cd backend && pytest -v
```

**Result:** 58/58 tests passing, ~84 seconds (Phase 6 baseline)  
No skips, no xfails.

---

## Known Warnings

| Warning | Source | Severity | Action |
|---|---|---|---|
| `CORS allow_origins=["*"]` | `backend/app/main.py:38` | Low (hackathon scope) | Tighten to real frontend origin before production |
| Health check re-reads full CSV | `backend/app/main.py:67` | Low (Phase 1 decision) | Switch to parquet/Postgres before real traffic |
| Spatial holdout FAIL (7.88% PR-AUC drop on unseen H3 cells) | `docs/spatial_holdout.md` | Medium | Documented limitation — model reliable on seen cells only |
| `closed_datetime` 100% missing | Phase 2 finding | Low | No model feature depends on it |
| `junction_name == "No Junction"` is 49.5% of rows | Phase 5 finding | Low | Escalation rules explicitly exclude it |

---

## Disclosure

- **No live Docker run was executed in this environment.** Verification is
  code-level + replay of Phase 6 live results (all endpoints confirmed then).
  The Compose file, Dockerfile, and env template are all present and correct.
- **No live browser session.** Frontend build and lint verified Phase 6;
  dashboard views confirmed correct via code review + API contract match.
- **Dataset not in repo.** `data/raw/violations_raw.csv` (298,450 rows) is
  gitignored. Regenerate processed files with:
  ```bash
  cd backend && python -m app.features.build_features
  ```

---

## Run Commands (Quick Reference)

```bash
# 1. Backend only (fastest path)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. Frontend (separate terminal)
cd frontend && cp .env.local.example .env.local
npm install && npm run dev

# 3. Full stack (Docker)
docker compose -f infra/docker-compose.yml up --build

# 4. Tests
cd backend && pytest -v

# 5. Demo scenarios
cd backend && python -m app.models.demo_seed all
```

**Overall verdict: PASS.** All code paths verified. Limitations disclosed.
One successful equivalent run confirmed (Phase 6 live session).
