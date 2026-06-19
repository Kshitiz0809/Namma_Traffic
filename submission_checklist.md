# Submission Checklist — v1.0-hackathon

Phase 7 Task 5. Every item verified against the actual repo state.
Check items manually before final submission.

---

## Repository Build

| Check | Status | Notes |
|---|---|---|
| `cd backend && pip install -r requirements.txt` | ✅ | All deps pinned in requirements.txt |
| `python -m app.features.build_features` | ✅ | Requires `data/raw/violations_raw.csv` |
| `python -m app.models.train` | ✅ | ~9 min; outputs to `ml/models/` |
| `uvicorn app.main:app --port 8000` | ✅ | Serves on port 8000 |
| `cd frontend && npm install && npm run dev` | ✅ | Serves on port 3000 |
| `cd frontend && npm run build` | ✅ | 113 kB first-load JS, 0 errors |
| `cd frontend && npm run lint` | ✅ | 0 warnings, 0 errors |
| `cd backend && pytest -v` | ✅ | 58/58 passing, ~84s |
| `docker compose -f infra/docker-compose.yml up --build` | ⚠ | Config verified; live run not executed in this env |

---

## Documentation

| Doc | Status | Path |
|---|---|---|
| Production README | ✅ | `README_FINAL.md` |
| Phase-by-phase build log | ✅ | `README.md` |
| Architecture decision records (21) | ✅ | `DECISIONS.md` |
| Model results report | ✅ | `MODEL_REPORT.md` |
| Feature dictionary | ✅ | `docs/feature_dictionary.md` |
| API contract | ✅ | `docs/api_contract.md` |
| Deployment instructions | ✅ | `docs/deployment.md` |
| Data quality report | ✅ | `docs/data_quality_report.{md,json}` |
| Baseline results + ablations | ✅ | `docs/baseline_results.md` |
| Spatial holdout analysis | ✅ | `docs/spatial_holdout.md` |
| Threshold selection | ✅ | `docs/threshold_selection.md` |
| Risk score definition | ✅ | `docs/risk_definition.md` |
| Demo scenarios | ✅ | `docs/demo_scenarios.md` |
| Run report | ✅ | `final_run_report.md` |
| Release notes | ✅ | `RELEASE_NOTES.md` |
| Final summary | ✅ | `FINAL_SUMMARY.md` |

---

## Secrets & Security

| Check | Status | Notes |
|---|---|---|
| No `.env` file committed | ✅ | `.gitignore` includes `.env` |
| `.env.example` present | ✅ | Root of repo — no real credentials |
| No hardcoded API keys in code | ✅ | `MAPBOX_ACCESS_TOKEN` is in env template, not code |
| No real dataset in repo | ✅ | `data/raw/` and `data/processed/` gitignored |
| `CORS allow_origins=["*"]` | ⚠ | Intentional for hackathon — tighten for production |
| No secrets in `docs/` or `slides/` | ✅ | Verified |

---

## Environment Template

| Check | Status | Notes |
|---|---|---|
| `.env.example` present at root | ✅ | All required vars documented |
| `frontend/.env.local.example` present | ✅ | `NEXT_PUBLIC_API_URL` documented |
| All vars have sensible defaults | ✅ | Local dev works without editing |
| Kafka/MLflow vars present (future phases) | ✅ | Commented in template |

---

## Presentation Assets

| Asset | Status | Path |
|---|---|---|
| Architecture diagram | ✅ | `docs/architecture_diagram.png` |
| System flow diagram | ✅ | `docs/system_flow.png` |
| PPT slide outline (12 slides) | ✅ | `docs/ppt_outline.md` |
| Slide speaker notes | ✅ | `slides/slide_notes.md` |
| Slides assets folder | ✅ | `slides/assets/` (created) |
| Calibration curve | ✅ | `docs/calibration_curve.png` |
| Threshold curve | ✅ | `docs/threshold_curve.png` |
| Forecast curves | ✅ | `docs/forecast_curves.png` |
| SHAP summary plot | ✅ | `docs/shap_summary.png` |
| Risk band examples (JSON) | ✅ | `docs/alerts.json` |
| Dashboard screenshots | ⚠ | Described in `docs/screenshots/README.md`; capture manually |

**Screenshot capture (manual step — ~10 min):**
```bash
# Start backend + frontend, then:
# 1. Open http://localhost:3000 → screenshot → slides/assets/screenshot_risk_map.png
# 2. Forecast panel with cell 89618925c03ffff → slides/assets/screenshot_forecast.png
# 3. Operations view → slides/assets/screenshot_operations.png
# 4. Analytics view → slides/assets/screenshot_analytics.png
```

---

## Demo Script

| Check | Status | Notes |
|---|---|---|
| Demo script written | ✅ | `docs/demo_script.md` |
| 3 real scenarios (no synthetic) | ✅ | `docs/demo_scenarios.md` |
| `demo_seed.py` tested | ✅ | Phase 6 — all 3 scenarios confirmed |
| Fallback plan if demo breaks | ✅ | `docs/alerts.json` walkthrough |
| Target length: 3-5 min | ✅ | Scripted at 4 min |

---

## Deployment Config

| Check | Status | Notes |
|---|---|---|
| `render.yaml` present | ✅ | Backend → Render |
| `frontend/vercel.json` present | ✅ | Frontend → Vercel |
| `infra/docker-compose.yml` present | ✅ | Full stack |
| `backend/Dockerfile` builds from repo root | ✅ | Context = `..` |
| No live deployment executed | ⚠ | Explicit scope decision — config is ready |

---

## Manual Steps Before Submission

- [ ] **Capture 4 dashboard screenshots** → `slides/assets/screenshot_*.png`
- [ ] **Run `pytest -v` one final time** to confirm 58/58 still pass
- [ ] **Verify repo has no uncommitted secrets** → `git status` + `git diff`
- [ ] **Confirm `.env` is not committed** → `git ls-files .env` (should return empty)
- [ ] **Tag the release** → `git tag v1.0-hackathon && git push origin v1.0-hackathon`
- [ ] **Push all Phase 7 files** → `git add . && git commit -m "Phase 7: Final submission packaging"`
- [ ] **Upload to submission portal** — include repo URL + `README_FINAL.md`
- [ ] **Optional: live deploy** → push `render.yaml` to Render, `vercel.json` to Vercel

---

## Overall Status

**READY FOR SUBMISSION** with the following manual steps outstanding:

1. Dashboard screenshots (10 min)
2. Final git tag + push
3. Submission portal upload

All code, docs, and deployment configs are complete.
