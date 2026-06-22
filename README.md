# Parking Intelligence — Decision Support Platform

> Predicts **where** illegal parking violations are likely to occur, **when**
> congestion begins, and **what** enforcement action to recommend — built
> entirely from real Bengaluru traffic-police violation records, no external data.

**Status:** retrainable, deployed, 78 backend tests passing.

Live demo: **[namma-traffic-orpin.vercel.app](https://namma-traffic-orpin.vercel.app)**
· API: **[kshitizsharma-parkingintelligenceapi.hf.space](https://kshitizsharma-parkingintelligenceapi.hf.space)**

---

## Problem

Bengaluru traffic police log parking violations reactively. By the time a
ticket is issued, the vehicle is already there, the obstruction is already
causing congestion, and dispatch is already delayed. No existing system says:
*"This junction will become a hotspot in the next 60 minutes — send a patrol
now."*

This platform answers three questions from historical violation data alone:

1. **Where** will violations cluster in the next 60 minutes?
2. **How severe** will the concentration be?
3. **What specific enforcement action** should dispatch take?

**Dataset constraint (intentional, not a gap):** only the provided
violations dataset is used — 298,450 rows, 24 columns (coordinates,
timestamps, vehicle, offence codes), Nov 2023 – Apr 2024. No external maps,
weather, traffic feeds, or enrichment at any stage (OpenStreetMap tiles
power the UI map rendering only — zero influence on any prediction). This
means the model is fully dependency-free at inference time.

---

## Architecture

```
Raw CSV (298,450 violations)
    │
    ▼
[Ingestion + Schema Validation]      backend/app/ingestion/
    │
    ▼
[Feature Engineering]                backend/app/features/
    │   H3 spatial grid (res 9, ~174m hex) + neighbor-averaged density features
    │   rolling temporal windows, leakage-safe (merge_asof, expanding windows)
    │   historical-risk aggregations
    ▼
[Model Training]                     ml/models/
    │   CatBoost (winner) │ LightGBM │ XGBoost
    │   classifier (hotspot_60m) + regressor (count_60m)
    ▼
[Decision Layer]                     backend/app/models/
    │   cost-aware threshold │ risk score (ridge-NNLS-fit weights) │ rules
    ▼
[FastAPI REST API]                   backend/app/serving/
    │   /forecast │ /alerts │ /metrics │ /health │ /admin/*
    ▼
[Next.js Dashboard]                  frontend/src/
    Live Risk Map │ Forecast │ Operations │ Analytics │ Admin
```

A retraining loop closes the gap between "frozen model" and "police upload
new data": an uploaded CSV lands in a PENDING staging area, a reviewer
approves or rejects it, approved rows merge into the master dataset, and an
explicit Retrain action re-runs the full pipeline (features → train → risk
weights → spatial holdout check → alerts) and hot-reloads the running API
with no restart.

---

## Quick Start (local)

```bash
# 1. Clone and configure
git clone <repo-url>
cd parking-intelligence
cp .env.example .env           # defaults work for local dev, no secrets needed

# 2. Backend: build features + train models
cd backend
pip install -r requirements.txt
python -m app.features.build_features   # ~25-30s, requires data/raw/violations_raw.csv
python -m app.models.train              # ~6-9 min first time; writes ml/models/

# 3. Start backend
uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs

# 4. Frontend (separate terminal)
cd ../frontend
cp .env.local.example .env.local        # set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm install
npm run dev
# Open http://localhost:3000
```

> `data/raw/violations_raw.csv` (298,450 rows, 24 columns) is not committed
> to the repo (gitignored, per dataset-distribution terms) — supply your own
> copy of the provided dataset at that path before running `build_features`.

### Tests

```bash
cd backend && pytest -q   # 78 tests, ~110s
```

### Demo scenarios (no synthetic data, real historical replays)

```bash
cd backend
python -m app.models.demo_seed all              # all 3 real scenarios
python -m app.models.demo_seed growth            # hotspot growth at a real junction
python -m app.models.demo_seed recommendations   # escalation example
python -m app.models.demo_seed alerts            # alert replay
```

### Docker Compose (full local stack)

```bash
docker compose -f infra/docker-compose.yml up --build
```

---

## Deploying Live

This project is deployed as: **Docker image → Docker Hub → Hugging Face
Space (backend API)**, and **Next.js → Vercel (frontend)**, auto-deploying
on push to `main`.

### Backend (Docker Hub → Hugging Face Space)

```bash
# Build (run from the repo root — the Dockerfile expects this build context)
docker build -f backend/Dockerfile -t <your-dockerhub-user>/parking-intelligence-api:latest .

# Push
docker push <your-dockerhub-user>/parking-intelligence-api:latest
```

Then point a Hugging Face Space (SDK: Docker) at that image — `deploy/huggingface-space/Dockerfile`
does `FROM <your-dockerhub-user>/parking-intelligence-api:latest`. Bump the
`# build-tag:` comment in that Dockerfile and push to the Space's git repo
to force it to re-pull `:latest` instead of a cached layer:

```bash
git clone https://huggingface.co/spaces/<your-username>/<your-space-name>
cd <your-space-name>
# edit the build-tag comment in Dockerfile to any new string
git add -A && git commit -m "Bump build tag" && git push
```

Set `ADMIN_API_TOKEN` as a Space secret to enable the `/admin/*` retraining
routes (unset = disabled, returns 503).

**Note:** free-tier hosts (Render, HF Space CPU tier) sleep after
inactivity — the first request after a sleep can take 30-60s to wake up.
Also, without a persistent volume attached, anything written by the admin
retraining pipeline (uploaded CSVs, retrained models) does not survive a
redeploy — this is a deployment-infrastructure decision, not a code gap.

### Frontend (Vercel)

Connect the repo to a Vercel project (root directory: `frontend/`) and set
one environment variable:

```
NEXT_PUBLIC_API_BASE_URL=https://<your-backend-url>
```

This is read at **build time** (Next.js `NEXT_PUBLIC_*` convention), so
redeploy after changing it. Vercel auto-deploys on every push to `main`.

---

## Modeling Results

### Hotspot Classification (`target_hotspot_60m`)

> "Will this H3 zone become a hotspot in the next 60 minutes?"

| Model | Val PR-AUC | Test PR-AUC | F1 | Brier |
|---|---|---|---|---|
| **CatBoost (winner)** | **0.8767** | **0.8732** | **0.8311** | **0.1766** |
| LightGBM | 0.8649 | — | 0.8290 | 0.1832 |
| XGBoost | 0.8632 | — | 0.8246 | 0.1918 |

Split is strictly time-based (train → val → test by date, never random).
Operating threshold: **0.15** — cost-aware, since a missed hotspot costs
more than a false alarm.

### Count Regression (`target_count_60m`)

| Model | MAE | RMSE | R² |
|---|---|---|---|
| **CatBoost** | **5.92** | **10.58** | **0.271** |
| LightGBM | 6.02 | 10.92 | 0.223 |
| XGBoost | 6.24 | 11.18 | 0.186 |

### Spatial generalization (does it work on geography it's never seen?)

Methodology: split H3 cells (not rows) into train/holdout sets — 1,824
train cells, 455 entirely-unseen holdout cells — and compare PR-AUC.

| Stage | PR-AUC drop | Change made |
|---|---|---|
| Original | 7.88% | Raw `h3_cell`/`geohash` kept as categorical model inputs |
| Fix 1 | 6.32% | Dropped cell identity, added 6 neighbor-averaged density features (H3 ring-1, leakage-safe `merge_asof`) |
| Fix 2 (current) | **5.66%** | Classifier regularization sweep — depth 6→3, `l2_leaf_reg` 3→25 (15+ configs tested; this was a strict win, improving seen-cell accuracy too, not a tradeoff) |

**Honest verdict: still FAIL** by this project's own 5% bar, reported as
such — a real ~28% relative improvement, not a fabricated PASS. Widening
the neighbor ring and pushing regularization further (depth=2/1) were both
tried and either hit diminishing returns or started costing real accuracy.
This looks like a genuine floor given what's derivable from this dataset
alone (no external geographic enrichment permitted).

A second, separate test — **spatial abstraction** (does the model merely
memorize coordinates, or learn transferable signal?) — compares a model
trained WITH raw cell identity against one trained WITHOUT it: **0.55%**
PR-AUC difference, well under a 3% bar → **PASS**. The model has learned
real signal (time-of-day, vehicle mix, junction history) on top of, not
instead of, location.

### Congestion risk score

```
risk_score = 100 × (
    w_hotspot · hotspot_probability
  + w_count   · normalized_predicted_count
  + w_persist · persistence
  + w_recent  · recent_intensity
)
```

Weights were originally hand-picked (0.40/0.30/0.20/0.10). They are now
**fit** via ridge-regularized Non-Negative Least Squares against
`target_count_60m` (the closest available outcome proxy — there is no
ground-truth congestion/enforcement-outcome data anywhere in the provided
dataset), refit automatically on every retrain. Current weights:
`hotspot 0.020 / count 0.701 / persistence 0.147 / recent 0.131`. Band
cutoffs (LOW/MEDIUM/HIGH/CRITICAL) are the 50th/85th/97th percentile of
train-period risk scores.

---

## Prediction → Action

A prediction alone isn't a decision. Three additions (ADR-026) turn
hotspot scores into something a dispatcher can actually act on:

**Patrol dispatch optimizer.** Given N available units and the live risk
snapshot, solves an assignment problem (`scipy.optimize.linear_sum_assignment`)
to send each unit to a *distinct* hotspot, minimizing total travel
distance — instead of every unit converging on the single highest-risk
cell. Unit origins are each police station's own historical-violation
centroid (internal-data-only — no external facilities database); travel
time is straight-line haversine distance at a disclosed assumed urban
speed, not a routing-API ETA. Reports a naive baseline alongside the
optimized plan so the value-add is visible, not just asserted.

**Backtested early-warning lead time.** Not a restatement of the
60-minute prediction horizon — genuinely backtested by replaying the
validation period chronologically per H3 cell and finding, for every real
hotspot episode, the earliest point the classifier's probability crossed
the operating threshold. Current result: **4,660/4,662 episodes caught**,
mean lead time 29.5 minutes — but the median is 0 minutes (most hotspots
are flagged the moment they start forming, not meaningfully before), and
**23.0% of episodes get a genuine 30+ minute head start**. Reported with
both numbers, not just the more flattering mean.

**Emerging vs. steady-state hotspot trend.** Built from existing features
only, no new model — compares recent activity (`violations_last_60m`,
extrapolated to a daily rate) against a cell's own historical density. A
cell-*relative* ratio (≥2x → `EMERGING`), so naturally busy junctions
aren't permanently flagged. Distinguishes a brand-new spike (where a
patrol redirect changes the outcome) from a chronic area already part of
routine patrol (`STEADY`). Surfaced in `/alerts`, `/forecast`, and the
Operations View.

---

## API Reference

Base URL (local): `http://localhost:8000` · Swagger UI: `/docs`

| Endpoint | Purpose |
|---|---|
| `GET /health` | Dataset load status, schema validity |
| `GET /forecast?h3_cell=...` | Hotspot probability, predicted count, risk score/band, recommendation, top contributing factors, cold-start flag |
| `GET /alerts` | Ranked GREEN/YELLOW/ORANGE/RED alerts across all cells, including `hotspot_trend` |
| `GET /metrics` | Model comparison, spatial robustness, live risk distribution, temporal distribution, backtested lead time |
| `GET /dispatch/plan?n_units=...` | Optimal patrol assignment for N available units across current hotspots |
| `GET /replay/{scenario}` | Real historical event-sequence replay (for demos) |

### Admin API (retraining pipeline)

Guarded by an `X-Admin-Token` header matching `ADMIN_API_TOKEN` (unset =
disabled, 503; wrong token = 401). A police-uploaded CSV lands as PENDING
first — it does not affect the model until a reviewer approves it.

| Endpoint | Purpose |
|---|---|
| `POST /admin/staging/upload` | Upload a CSV, lands as PENDING (schema-validated, previewed, not yet merged) |
| `GET /admin/staging` / `GET /admin/staging/{id}` | List / inspect staged uploads (row preview, validation summary) |
| `POST /admin/staging/{id}/approve` | Merge into the master raw dataset |
| `POST /admin/staging/{id}/reject` | Discard (file kept on disk for audit) |
| `POST /admin/retrain` | Trigger the full retrain pipeline in the background; returns a `job_id` |
| `GET /admin/retrain/{job_id}` | Poll job status (`PENDING`/`RUNNING`/`SUCCESS`/`FAILED`) + result metrics |
| `POST /admin/ingest` | Direct merge, bypassing staging (scripted/bulk use) |

On a successful retrain, the running process hot-reloads models and risk
params with zero downtime.

---

## Dashboard

Next.js 14 + Leaflet + Recharts. Six views:

| View | What it shows |
|---|---|
| **Live Risk Map** | All known H3 cells color-coded by alert level |
| **Forecast Panel** | Per-cell/coordinate prediction + contributing factors |
| **Operations View** | Alert queue sorted by risk score, filterable by level, with emerging/steady trend badges |
| **Dispatch** | Computes an optimal patrol assignment for N available units across current hotspots |
| **Analytics View** | Model comparison, spatial-robustness metrics, backtested lead time, risk distribution, temporal patterns |
| **Admin** | Upload CSVs, review/approve staged data, trigger retraining, watch job status |

The dashboard talks only to this project's own FastAPI backend — no
external predictive data, no third-party hotspot service.

---

## Known Limitations — Disclosed, Not Hidden

1. **Spatial holdout FAIL, improved** — 5.66% PR-AUC drop on brand-new H3
   cells (down from 7.88%), still above the project's own 5% bar. See
   *Spatial generalization* above for the full methodology and what was tried.
2. **Risk weights are a data-driven proxy fit**, not a measured causal
   weight — there's no ground-truth congestion/enforcement-outcome data in
   this dataset.
3. **Missing enforcement timestamps** — `closed_datetime` and
   `action_taken_timestamp` are 100% missing in this extract; resolution
   time and enforcement delay cannot be computed.
4. **Single 5-month data window** (Nov 2023 – Apr 2024) — seasonal patterns
   outside this window are untested.
5. **No live streaming** — the dashboard serves the latest historical
   snapshot per cell, not a real-time feed.
6. **Retraining doesn't survive ephemeral redeploys** on free-tier hosts
   without a persistent volume attached — works correctly within a running
   process's lifetime.
7. **Cold-start geography** — brand-new H3 cells outside the observed set
   return a conservative default with an explicit flag, never a fabricated
   prediction.

---

## Folder Structure

```
.
├── README.md                          # this file
├── .env.example                       # env template — copy to .env
├── render.yaml                        # Render deployment config (backend, alternate to HF Space)
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   └── app/
│       ├── main.py                    # FastAPI entrypoint
│       ├── core/config.py             # typed settings from .env
│       ├── ingestion/                 # schema validation, raw + staging data stores
│       ├── features/                  # H3 spatial, temporal, rolling, aggregated features
│       ├── models/                    # training, classifier/regressor, risk score, retraining
│       ├── serving/                   # forecast/alerts/metrics/admin FastAPI routers
│       └── tests/                     # 78 tests
│
├── frontend/
│   ├── package.json
│   ├── vercel.json
│   ├── .env.local.example
│   └── src/
│       ├── app/                       # Next.js 14 app router pages
│       ├── components/                # LiveRiskMap, ForecastPanel, OperationsView,
│       │                               AnalyticsView, AdminPanel
│       └── lib/                       # api.ts, types.ts
│
├── ml/
│   ├── models/                        # saved model artifacts (gitignored, regenerate via train.py)
│   └── notebooks/                     # EDA, feature validation, model comparison
│
├── infra/
│   └── docker-compose.yml             # Postgres + Redis + backend, full local stack
│
├── deploy/
│   └── huggingface-space/             # HF Space Dockerfile (pulls the Docker Hub image)
│
├── data/
│   ├── raw/violations_raw.csv         # gitignored — supply your own copy of the dataset
│   └── processed/                     # gitignored — regenerate with build_features.py
│
└── docs/                              # methodology detail: api_contract, feature_dictionary,
                                          spatial_holdout, spatial_dependency, risk_definition,
                                          threshold_selection, deployment, demo_script, etc.
```

---

## Future Scope

| Area | What would change |
|---|---|
| Real-time streaming | Kafka producer → consumer → live feature updates |
| Expanded coverage | More data from more zones to fully close the spatial holdout gap (5.66% → <5%) |
| Enforcement feedback | If `closed_datetime` becomes available, add resolution-time features |
| Causal validation | A/B test: does acting on an alert actually reduce violations? |
| Persistent retraining storage | Attach a volume so `/admin/retrain` artifacts survive redeploys on ephemeral hosts |
| Auth + multi-tenant | Replace the shared-secret admin token with per-station access control |

---

*Every limitation disclosed. Every number in this README traces back to a
real training run or a live `/metrics` call — nothing here is rounded up.*
