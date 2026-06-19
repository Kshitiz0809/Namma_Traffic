# Parking Intelligence + Predictive Alert Platform

> Predicts **where** illegal parking violations are likely to occur, **when**
> congestion begins, and **what** enforcement action to recommend — built
> entirely from real Bengaluru traffic-police violation records, no external data.

**Status:** v1.0-hackathon — all 6 modeling phases complete, 58 tests passing.

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

---

## Architecture

```
Raw CSV (298,450 violations)
    │
    ▼
[Ingestion + Schema Validation]
    │  backend/app/ingestion/
    ▼
[Feature Engineering]  ──────── H3 spatial (res 9, ~174m hex)
    │  backend/app/features/     rolling temporal windows
    ▼                            historical-risk aggregations
[Model Training]
    │  ml/models/               CatBoost (winner) │ LightGBM │ XGBoost
    ▼                           classifier (hotspot_60m) + regressor (count_60m)
[Decision Layer]
    │  backend/app/models/      cost-aware threshold │ risk score │ rules
    ▼
[FastAPI REST API]
    │  backend/app/serving/     /forecast │ /alerts │ /metrics │ /health
    ▼
[Next.js Dashboard]
       frontend/src/            Live Risk Map │ Forecast │ Operations │ Analytics
```

Full diagram: [`docs/architecture_diagram.png`](docs/architecture_diagram.png)  
System flow: [`docs/system_flow.png`](docs/system_flow.png)

---

## Dataset Constraints

**Internal-data-only** (ADR-001 — intentional, not a gap):

- Source: Bengaluru traffic-police violation records, Nov 2023 – Apr 2024
- 298,450 rows, 24 columns (coordinates, timestamps, vehicle, offence codes)
- No external maps, weather, traffic feeds, or enrichment at any stage
- OpenStreetMap tiles power the UI map rendering only — zero influence on
  any prediction

This means the model is fully dependency-free at inference time. A fresher
CSV export is the only thing needed to update predictions.

---

## Quick Start

```bash
# 1. Clone and configure
git clone <repo-url>
cp .env.example .env           # no secrets needed for local dev defaults

# 2. Build features (requires data/raw/violations_raw.csv — see Dataset below)
cd backend
pip install -r requirements.txt
python -m app.features.build_features

# 3. Train models (~9 min first time; pre-trained artifacts in ml/models/)
python -m app.models.train

# 4. Start backend
uvicorn app.main:app --reload --port 8000

# 5. Start dashboard (separate terminal)
cd ../frontend && cp .env.local.example .env.local
npm install && npm run dev
# Open http://localhost:3000
```

---

## Folder Structure

```
.
├── .env.example                      # env template — copy to .env
├── .gitignore
├── README.md                         # phase-by-phase build log
├── README_FINAL.md                   # this file — submission README
├── DECISIONS.md                      # 21 architecture decision records
├── MODEL_REPORT.md                   # model results + limitations
├── RELEASE_NOTES.md                  # v1.0-hackathon changelog
├── FINAL_SUMMARY.md                  # one-page summary for judges
├── final_run_report.md               # Phase 7 verification report
├── render.yaml                       # Render deployment config (backend)
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   └── app/
│       ├── main.py                   # FastAPI entrypoint
│       ├── core/config.py            # typed settings from .env
│       ├── ingestion/
│       │   ├── schema.py             # 24-column contract + Bengaluru bbox
│       │   ├── load_data.py          # loads + validates raw CSV
│       │   └── data_audit.py         # generates docs/data_quality_report.*
│       ├── features/
│       │   ├── build_features.py     # pipeline orchestrator
│       │   ├── cleaning.py           # NULL normalization, dtype coercion
│       │   ├── spatial.py            # H3 (res 9) + GeoHash binning
│       │   ├── temporal.py           # hour, day, month, cyclic encodings
│       │   ├── rolling.py            # leakage-safe windowed counts
│       │   ├── aggregated.py         # historical-risk aggregations
│       │   ├── operational.py        # multi-offence parsing, device features
│       │   └── targets.py            # hotspot/count targets at 15/30/60/90m
│       ├── models/
│       │   ├── train.py              # full training orchestrator
│       │   ├── classifier.py         # CatBoost/LightGBM/XGBoost hotspot model
│       │   ├── regressor.py          # count regression models
│       │   ├── split.py              # time-based train/val/test split
│       │   ├── feature_set.py        # live-prediction-safe feature list
│       │   ├── threshold_optimization.py  # cost-aware threshold sweep
│       │   ├── calibration.py        # Platt/Isotonic calibration (tested, not adopted)
│       │   ├── spatial_holdout.py    # H3-cell-level holdout experiment
│       │   ├── multi_horizon.py      # 15/30/60/90m comparison
│       │   ├── shap_audit.py         # bootstrap SHAP stability
│       │   ├── harden.py             # Phase 3.5 orchestrator
│       │   ├── congestion_score.py   # derived risk score (not a new ML target)
│       │   ├── risk_score.py         # 0-100 risk_score with band cutoffs
│       │   ├── recommendation.py     # rule-based enforcement recommendation
│       │   ├── alerts.py             # GREEN/YELLOW/ORANGE/RED alert generator
│       │   ├── explain.py            # SHAP explanations
│       │   └── demo_seed.py          # 3 real demo scenarios (no synthetic data)
│       ├── serving/
│       │   ├── forecast_service.py   # GET /forecast
│       │   ├── alerts_service.py     # GET /alerts
│       │   ├── metrics_service.py    # GET /metrics
│       │   └── risk_snapshot.py      # snapshot builder for /metrics
│       └── tests/                    # 58 tests across all phases
│
├── frontend/
│   ├── package.json
│   ├── vercel.json                   # Vercel deployment config
│   ├── .env.local.example
│   └── src/
│       └── app/                      # Next.js 14 app router pages + components
│
├── ml/
│   ├── models/                       # 6 saved model artifacts (gitignored if large)
│   ├── notebooks/
│   │   ├── 01_eda.ipynb
│   │   ├── 02_feature_validation.ipynb
│   │   ├── 03_model_comparison.ipynb
│   │   └── simulator.ipynb
│   └── requirements.txt
│
├── infra/
│   └── docker-compose.yml            # Postgres + Redis + backend
│
├── data/
│   ├── raw/violations_raw.csv        # gitignored — 298,450 rows
│   └── processed/                    # gitignored — regenerate with build_features.py
│
└── docs/
    ├── api_contract.md
    ├── architecture_diagram.png
    ├── system_flow.png
    ├── baseline_results.md           # full model comparison, ablations, SHAP
    ├── data_quality_report.{md,json}
    ├── feature_dictionary.md
    ├── spatial_holdout.md
    ├── spatial_dependency.md
    ├── threshold_selection.md
    ├── risk_definition.md
    ├── recommendation_rules.yaml
    ├── demo_scenarios.md
    ├── demo_script.md
    ├── deployment.md
    ├── ppt_outline.md
    ├── final_checklist.md
    └── leaderboard.csv
```

---

## Model Results

### Primary Objective — Hotspot Classification (`target_hotspot_60m`)

> "Will this H3 zone become a hotspot in the next 60 minutes?"

| Model | Val PR-AUC | Test PR-AUC | F1 | Brier |
|---|---|---|---|---|
| **CatBoost** | **0.8767** | **0.8732** | **0.8311** | **0.1766** |
| LightGBM | 0.8649 | — | 0.8290 | 0.1832 |
| XGBoost | 0.8632 | — | 0.8246 | 0.1918 |

**Split:** time-based (train → 2024-02-19, val → 2024-03-14, test → 2024-04-08).
Never random. Test touched exactly once with the already-chosen winner.

**Decision threshold:** 0.15 (cost-aware — false negatives weighted 3× worse
than false positives; see `docs/threshold_selection.md`).

### Secondary Objective — Count Regression (`target_count_60m`)

| Model | MAE | R² |
|---|---|---|
| **CatBoost** | **5.92** | **0.271** |

### Risk Distribution (validation set, 44,767 rows)

| Band | Count | % |
|---|---|---|
| LOW | 26,013 | 58.1% |
| MEDIUM | 12,352 | 27.6% |
| HIGH | 5,327 | 11.9% |
| CRITICAL | 1,075 | 2.4% |

### Key Hardening Results

| Experiment | Result | Decision |
|---|---|---|
| Cost-aware threshold | 0.30 → **0.15** | Adopted |
| Platt/Isotonic calibration | < 5% Brier improvement | Rejected — bar not cleared |
| **Spatial holdout (unseen H3 cells)** | 7.88% PR-AUC drop (original) → **6.32% after ADR-022** | **FAIL — improved, not fully cleared (5% bar)** |
| Remove `h3_cell`/`geohash` + add neighbor-averaged features (ADR-022) | Drop reduced 7.09%→6.32% (ring-2/3 and dropping more categoricals tried, no further gain) | Adopted as production default |
| Risk score weights | Hand-picked (0.40/0.30/0.20/0.10) → fit via ridge-regularized NNLS against `target_count_60m` (ADR-023) | Adopted; refit on every retrain |

---

## API Docs

Base URL (local): `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs` (Swagger UI)

### GET /health
Returns dataset load status and schema validity.

```json
{ "status": "ok", "rows_loaded": 298450, "schema_valid": true, "missing_columns": [] }
```

### GET /forecast
Predict hotspot probability and enforcement recommendation for an H3 cell.

**Query params:** `h3_cell` (required), `vehicle_type` (optional override)

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

Cold-start cells (never seen in training) return `is_cold_start: true` with
a conservative default — no fabricated probability.

### GET /alerts
Returns top alerts sorted by `risk_score` descending.

**Query params:** `limit` (default 20), `min_level` (GREEN/YELLOW/ORANGE/RED)

```json
{
  "alerts": [
    {
      "zone": "89618925c03ffff",
      "junction_name": "Safina Plaza Junction",
      "police_station": "...",
      "lat": 12.9876, "lon": 77.5432,
      "alert_level": "ORANGE",
      "probability": 0.72,
      "risk_score": 61.3,
      "risk_band": "HIGH",
      "recommendation": "Deploy enforcement",
      "escalated": false,
      "top_contributing_factors": ["rolling_hotspot_intensity", "violations_last_15m"],
      "last_known_event": "2024-04-08T17:30:00"
    }
  ],
  "total_cells_evaluated": 2534
}
```

### GET /metrics
Returns model leaderboard + live risk distribution snapshot.

### Admin API (retraining — ADR-024)

Closes the "frozen model" gap: police-uploaded CSVs can be ingested and the
full pipeline (features → models → risk params → spatial holdout check)
retrained without redeploying. Guarded by an `X-Admin-Token` header
matching `ADMIN_API_TOKEN` (unset = disabled, 503).

| Endpoint | What it does |
|---|---|
| `POST /admin/ingest` | Upload a new violations CSV; validates schema, dedupes by `id` against the master raw store, appends. Does not retrain by itself. |
| `POST /admin/retrain` | Triggers the full retrain pipeline in the background; returns a `job_id` immediately. |
| `GET /admin/retrain/{job_id}` | Poll job status (`PENDING`/`RUNNING`/`SUCCESS`/`FAILED`) + result metrics. |

On success, the running process hot-reloads models/risk params without a
restart. Known limitation: on ephemeral-filesystem hosts (Render/HF Space
free tier), the master raw CSV and retrained artifacts won't survive a
redeploy unless a persistent volume is attached.

---

## Dashboard

Built with Next.js 14 + Leaflet. Four views:

| View | What it shows |
|---|---|
| **Live Risk Map** | All 2,534 known H3 cells color-coded by alert level |
| **Forecast Panel** | Per-cell prediction + contributing factors lookup |
| **Operations View** | Alert queue sorted by risk score, filterable by level |
| **Analytics View** | Model comparison, calibration, horizon charts |

Dashboard talks only to the local FastAPI backend. No external predictive
data, no third-party hotspot service.

---

## Limitations

These are disclosed upfront, not buried in an appendix:

1. **Cold-start geography** — model was trained on 2,534 H3 cells seen in the
   dataset. For brand-new cells (new enforcement zones), the API returns a
   conservative default. The retraining pipeline (ADR-024, see Admin API
   above) lets new coverage be incorporated without a manual redeploy.

2. **Spatial holdout FAIL, improved** — on a held-out set of H3 cells with
   zero training history, PR-AUC dropped 7.88% originally; ADR-022 (dropping
   raw `h3_cell`/`geohash` as model inputs + adding neighbor-averaged
   density/intensity features) reduced this to **6.32%** — a real ~20%
   relative improvement, but still above the project's own 5% acceptance bar.
   Widening the neighbor ring and dropping further location-correlated
   categoricals were tried and didn't move it further — this looks like a
   genuine floor given what's derivable from this dataset alone (no external
   geographic data permitted), not a tuning oversight.

3. **Missing enforcement timestamps** — `closed_datetime` and
   `action_taken_timestamp` are 100% missing in this extract. Resolution time
   and enforcement delay cannot be computed.

4. **Single data extract** — data covers Nov 2023 – Apr 2024 only. Seasonal
   patterns outside this window are untested.

5. **Risk weights are fit, not assumed (ADR-023)** — `risk_score` weights
   were originally hand-picked (0.40/0.30/0.20/0.10); they're now fit via
   ridge-regularized NNLS against `target_count_60m` (the best available
   outcome proxy — there's still no ground-truth congestion/enforcement
   data in this dataset) and refit automatically on every retrain. Still a
   proxy fit, not a measured causal weight.

6. **No live streaming** — dashboard shows the latest historical snapshot per
   cell, not a real-time feed. A Kafka streaming layer is the natural next step.

7. **Retraining doesn't survive ephemeral redeploys** — the admin retrain
   pipeline (ADR-024) works correctly within a running process's lifetime,
   but on free-tier hosts without a persistent volume, the appended raw data
   and retrained models are lost on the next redeploy. Attaching a volume is
   a deployment-infrastructure decision, not a code gap.

---

## Future Scope

| Area | What would change |
|---|---|
| **Real-time streaming** | Kafka producer → consumer → live feature updates |
| **Expanded coverage** | More data from more zones to fully close the spatial holdout gap (6.32% → <5%) |
| **Enforcement feedback** | If `closed_datetime` becomes available, add resolution-time features |
| **Causal validation** | A/B test: does acting on an alert actually reduce violations? |
| **Persistent retraining storage** | Attach a volume so `/admin/retrain` artifacts survive redeploys on ephemeral hosts |
| **Auth + multi-tenant** | Replace the shared-secret admin token with per-station access control |

---

## Setup (Full Detail)

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker + Docker Compose (optional — for full stack)
- `data/raw/violations_raw.csv` (298,450 rows, 24 columns — not in repo)

### Environment

```bash
cp .env.example .env
# Edit .env if needed — defaults work for local dev
```

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m app.features.build_features   # ~25-28 seconds
python -m app.models.train              # ~9 minutes (first time)
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
# Verify NEXT_PUBLIC_API_URL=http://localhost:8000 in .env.local
npm install
npm run dev      # dev server at http://localhost:3000
npm run build    # production build (optional — 113 kB first-load JS)
```

### Docker Compose

```bash
docker compose -f infra/docker-compose.yml up --build
```

### Tests

```bash
cd backend && pytest -v   # 58 tests, ~84 seconds
```

### Demo Scenarios

```bash
cd backend
python -m app.models.demo_seed all           # all 3 real scenarios
python -m app.models.demo_seed growth        # hotspot growth at Elite Junction
python -m app.models.demo_seed recommendations   # escalation at Safina Plaza
python -m app.models.demo_seed alerts        # alert replay
```

---

## Deployment

Full instructions: [`docs/deployment.md`](docs/deployment.md)

- **Backend → Hugging Face Space (Docker)**: https://kshitizsharma-parkingintelligenceapi.hf.space
  — `deploy/huggingface-space/` pulls the prebuilt `kshitizs98/parking-intelligence-api`
  Docker Hub image (`backend/Dockerfile` builds it from repo root context).
  Render was tried first but its free tier's 512MB RAM OOM-killed `/metrics`
  and `/alerts`; HF's free CPU tier (16GB RAM) fixed it.
- **Frontend → Vercel**: https://namma-traffic-orpin.vercel.app

**Note for judges:** the backend is on Hugging Face's free CPU tier, which
sleeps after a period of inactivity. The first request after a sleep can take
30-60s to wake up — if the dashboard looks stuck on "Loading…" on first load,
give it a minute and refresh.

---

*Built in 6 phases. Every limitation disclosed. Every number from a real run.*
