# Release Notes — v1.0-hackathon

**Release date:** 2026-06-17  
**Branch:** master  
**Tag:** v1.0-hackathon

---

## What This Release Is

A complete, end-to-end parking-violation hotspot prediction and enforcement
recommendation platform, built in 6 phases from a single internal dataset
(298,450 Bengaluru traffic-police violation records, Nov 2023 – Apr 2024).

This is a hackathon submission freeze. No further modeling changes will be made
to this version. The feature set, models, thresholds, and risk formula are all
locked per Phase 4 decision.

---

## What Works

### Backend (FastAPI)
- `GET /health` — dataset load + schema validation
- `GET /forecast?h3_cell=<id>` — hotspot probability, count estimate, risk band,
  enforcement recommendation, cold-start handling
- `GET /alerts?limit=N&min_level=X` — top alerts sorted by risk score
- `GET /metrics` — model leaderboard + live risk distribution
- `GET /docs` — Swagger UI (auto-generated)

### Frontend (Next.js 14 + Leaflet)
- Live Risk Map — 2,534 H3 cells color-coded by alert level
- Forecast Panel — per-cell prediction lookup
- Operations View — alert queue, filterable by severity
- Analytics View — model comparison, calibration, horizon charts

### ML Pipeline
- Feature engineering: 56 columns from 24 raw (H3 spatial, rolling temporal,
  historical-risk aggregations, leakage-safe throughout)
- CatBoost classifier: `target_hotspot_60m`, Val PR-AUC 0.8767, Test PR-AUC 0.8732
- CatBoost regressor: `target_count_60m`, MAE 5.92, R² 0.271
- Cost-aware threshold: 0.15 (FN weighted 3× FP)
- Risk score: 0-100 derived signal, 4 bands (LOW/MEDIUM/HIGH/CRITICAL)
- Rule-based recommendation: Monitor/Patrol/Deploy enforcement/Tow candidate
- Demo mode: 3 real scenarios (not synthetic)

### Tests
- 58/58 backend tests passing
- Covers: ingestion, feature engineering (including brute-force leakage checks),
  model training sanity, serving endpoints, cold-start behavior

### Deployment Config
- `render.yaml` (backend → Render)
- `frontend/vercel.json` (frontend → Vercel)
- `infra/docker-compose.yml` (full local stack)
- `backend/Dockerfile` (repo-root build context)

---

## Known Limitations (Disclosed, Not Fixed in This Release)

1. **Spatial holdout FAIL, improved (Phase 8 / ADR-022 + ADR-025)** —
   originally 7.88% PR-AUC drop on H3 cells with zero training history;
   dropping raw `h3_cell`/`geohash` as model inputs and adding
   neighbor-averaged density/intensity features reduced this to 6.32%
   (ADR-022), and a classifier regularization sweep (depth=6→3,
   l2_leaf_reg=3→25) reduced it further to **5.66%** (ADR-025) — a real
   ~28% relative improvement, still above the project's own 5% bar. Model
   generalizes well within observed area, not fully to brand-new zones.
   The Phase 8 retraining pipeline (Admin tab → upload → approve →
   retrain) lets new coverage be incorporated without a manual rebuild.

2. **No live streaming** — dashboard serves latest historical snapshot per cell,
   not a real-time feed. Kafka config is in `.env.example` for a future phase.

3. **`closed_datetime` 100% missing** — enforcement resolution time cannot be
   computed from this data extract. Feature is documented as unavailable.

4. **Single data extract** — 5 months only (Nov 2023 – Apr 2024). Seasonal
   patterns outside this window are untested.

5. **Risk weights are fit, not assumed (Phase 8 / ADR-023)** — originally
   hand-picked (0.40/0.30/0.20/0.10); now fit via ridge-regularized NNLS
   against `target_count_60m` (the best available outcome proxy — still no
   ground-truth congestion/enforcement data exists in this dataset), and
   refit automatically on every retrain. Still a proxy fit, not a measured
   causal weight.

6. **CORS is open** — `allow_origins=["*"]` is intentional for demo purposes.
   Tighten to the real frontend origin before any production use.

7. **Retraining doesn't survive ephemeral redeploys (Phase 8 / ADR-024)** —
   the admin retrain pipeline works correctly within a running process's
   lifetime, but on free-tier hosts without a persistent volume, the
   appended raw data and retrained artifacts are lost on the next redeploy.

---

## Files Added in Phase 7 (This Release)

```
final_run_report.md          — local verification report
README_FINAL.md              — production-grade submission README
submission_checklist.md      — pre-submission verification checklist
RELEASE_NOTES.md             — this file
FINAL_SUMMARY.md             — one-page judge summary
slides/
  slide_notes.md             — speaker notes for all 12 slides
  assets/                    — placeholder for dashboard screenshots
```

---

## Files Changed in Phase 7

- `infra/docker-compose.yml` — updated comment header (Phase 7 note)

No model files, feature pipelines, or API endpoints were modified in Phase 7.
The modeling codebase was frozen as of Phase 4 — until Phase 8 (below)
deliberately revisited that freeze.

---

## Phase 8 — Retraining pipeline, spatial generalization fix, data-fit risk weights

Closes three gaps identified in post-submission review: the model couldn't
be retrained on new data, the spatial holdout test still failed, and the
risk score weights were hand-picked rather than fit. Full reasoning in
`DECISIONS.md` ADR-022/023/024.

**Changed:**
- `backend/app/features/spatial.py` / `rolling.py` — new
  `add_neighbor_averaged_features`: H3 ring-1 neighbor-averaged density/
  intensity features (6 new columns), leakage-safe via `merge_asof`.
- `backend/app/models/feature_set.py` — `REDUCED_SPATIAL_CATEGORICAL_FEATURES`
  (already defined, previously unused) is now the production categorical
  set; `h3_cell`/`geohash` dropped as model inputs (kept as dataframe
  columns for serving lookups).
- `backend/app/models/risk_score.py` — `fit_risk_params`/`fit_risk_weights`
  (ridge-regularized NNLS) replace the hardcoded `WEIGHTS`/`RISK_BANDS`
  constants; bundled into one `RiskParams` artifact (`ml/models/risk_params.json`).
- `backend/app/models/train.py` — now also refits risk params and re-runs
  the spatial holdout check on every training run, writing
  `docs/spatial_holdout_result.json` fresh each time.
- New: `backend/app/ingestion/raw_store.py` (master raw CSV, dedupe/append),
  `backend/app/models/retrain.py` (pipeline orchestrator + artifact
  archiving), `backend/app/serving/admin_service.py` (`POST /admin/ingest`,
  `POST /admin/retrain`, `GET /admin/retrain/{job_id}`, guarded by
  `X-Admin-Token`).
- `forecast_service.py`/`risk_snapshot.py`/`metrics_service.py` — added
  `reload_state()` so a running process picks up retrained
  models/params without a restart.

**Result:** spatial holdout PR-AUC drop 7.88% → 6.32% (improved, not fully
passed); risk weights now `{hotspot_probability: 0.023,
normalized_predicted_count: 0.701, persistence: 0.145, recent_intensity:
0.131}` instead of hand-picked 0.40/0.30/0.20/0.10; 72/72 tests pass
(58 original + 14 new for raw_store/admin_service).

---

## How to Reproduce

```bash
# Requires: Python 3.10+, Node.js 18+, data/raw/violations_raw.csv

cp .env.example .env
cd backend
pip install -r requirements.txt
python -m app.features.build_features   # 25-28 sec
python -m app.models.train              # ~9 min
uvicorn app.main:app --port 8000

# Separate terminal:
cd frontend && cp .env.local.example .env.local
npm install && npm run dev              # http://localhost:3000
```

---

## Changelog vs Phase 6

| Area | Change |
|---|---|
| Modeling | None — feature set and models frozen |
| API | None |
| Dashboard | None |
| Docs | 5 new submission artifacts (this file + 4 others) |
| Slides | `slides/slide_notes.md` added |
| Tests | 58/58 — no change from Phase 6 |
