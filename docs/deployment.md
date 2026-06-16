# Deployment Guide

Phase 6 Task 3. **This is a prepare-only deliverable** — all configs/Dockerfiles
below are deploy-ready, but no live deployment was performed (no Render/Vercel
account credentials available in this environment). Follow these steps to
actually deploy.

No production secrets are included anywhere in this repo (explicit instruction).

---

## Before you deploy — REQUIRED pre-deploy step

The trained models, processed data, and several generated docs are
**gitignored by design** (`.gitignore` — they're regenerable build
artifacts, not source). The deployed backend needs them to exist in the
Docker build context. **Before building/deploying, run the full pipeline
locally** (or in a CI step) to produce them:

```bash
cd backend
python -m app.features.build_features        # -> data/processed/{features,targets}.parquet
python -m app.models.train                    # -> ml/models/{classifier,regressor}_*.{cbm,txt,json}, docs/leaderboard.csv
python -m app.models.harden                   # -> docs/threshold_*, calibration_*, spatial_holdout.md, etc.
python -m app.models.generate_phase5_artifacts  # -> docs/alerts.json + ml/models/risk_minmax_params.json (already committed)
```

This takes roughly 15-20 minutes total (see MODEL_REPORT.md for per-step
timings). The feature set is FROZEN (ADR-019) — this regenerates the same
artifacts deterministically, it does not retrain a different model.

---

## Backend → Render

1. Push this repo to GitHub (Render deploys from a Git remote).
2. In Render: **New → Blueprint** → select this repo → Render reads
   `render.yaml` from the repo root automatically. Or configure manually:
   - **Runtime**: Docker
   - **Dockerfile path**: `backend/Dockerfile`
   - **Docker build context**: repo root (`.`) — **not** `backend/`. The
     Dockerfile copies `ml/`, `data/`, `docs/` as siblings of `backend/`
     inside the image; building with `backend/` as context will fail to
     find them.
   - **Health check path**: `/health`
3. Environment variables to set in the Render dashboard (none are secrets):
   | Key | Value |
   |---|---|
   | `APP_ENV` | `production` |
   | `LOG_LEVEL` | `INFO` |
   `PORT` is injected automatically by Render — the Dockerfile's `CMD`
   already reads `$PORT` (defaults to 8000 for local `docker run`).
4. After deploy, verify: `curl https://<your-render-url>/health`

### Local Docker verification (recommended before pushing to Render)
```bash
# From the REPO ROOT (not backend/):
docker build -f backend/Dockerfile -t parking-intelligence-api .
docker run -p 8000:8000 parking-intelligence-api
curl http://localhost:8000/health
```
**Note**: this image installs CatBoost/LightGBM/XGBoost/SHAP and is
correspondingly large (likely 1GB+). It was not built/verified in this
environment due to a disk-space constraint at the time of writing
(<250MB free) — review the Dockerfile carefully before your first real
build, and budget disk space accordingly.

---

## Frontend → Vercel

1. In Vercel: **New Project** → import this repo → set **Root Directory**
   to `frontend/` (Vercel auto-detects Next.js from there; `frontend/vercel.json`
   pins the build/dev/install commands explicitly for clarity).
2. Environment variable to set in the Vercel dashboard:
   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | Your deployed Render URL, e.g. `https://parking-intelligence-api.onrender.com` |
3. Deploy. Vercel builds and serves automatically on every push to the
   connected branch.

### Local verification before deploying
```bash
cd frontend
npm install
npm run build   # must succeed — this was verified in this environment
npm run dev     # http://localhost:3000, with NEXT_PUBLIC_API_BASE_URL in .env.local
```

---

## `env.example` summary

Two env files exist, one per service (not consolidated into one root file,
since they're consumed by entirely different runtimes):

- **`.env.example`** (repo root, backend) — Postgres/Redis/Kafka/MLflow
  placeholders from earlier phases (most unused by the current frozen
  pipeline; kept for forward-compatibility with Phase 7+) plus
  `MAPBOX_ACCESS_TOKEN` (empty — Leaflet+OSM needs no key, per ADR-002/README).
- **`frontend/.env.local.example`** — just `NEXT_PUBLIC_API_BASE_URL`.

Copy each to its non-`.example` name and fill in real values for local dev;
set the equivalents directly in the Render/Vercel dashboards for deployed
environments. **No file in this repo contains a real secret.**

---

## CORS

The backend's `allow_origins=["*"]` (see `backend/app/main.py`) means the
deployed Vercel frontend will be able to call the deployed Render backend
with no further CORS configuration needed. Tighten this to the specific
Vercel origin before any production use beyond a demo.

---

## What's NOT included in this deployment prep

- **CI/CD pipeline** to auto-run the pre-deploy training step on every push
  — out of scope for Phase 6; the manual steps above work for a demo.
- **Persistent storage / database** — the API currently reads parquet files
  bundled into the Docker image at build time, not a live database. Fine
  for a frozen-model demo; would need revisiting for Phase 7's streaming work.
- **Actual live deployment** — per the explicit scoping decision for this
  phase, this document prepares everything needed; running it through
  Render/Vercel's actual dashboards is a step for whoever holds those
  account credentials.
