# Presentation Outline (10-12 slides)

Phase 6 Task 5. Each slide lists its purpose, the real artifact/number to
put on it, and a one-line speaker note. Everything cited is a real result
from this repo — no placeholder numbers.

---

### Slide 1 — Title
**Parking Intelligence + Predictive Alert Platform**
Subtitle: *Parking-Induced Congestion Risk Engine* (renamed Phase 5 — risk
derived from parking behavior, not measured traffic).
Speaker note: name, team, hackathon name/date.

### Slide 2 — Problem
- Illegal parking creates localized congestion that's reactive, not
  predictive, in most enforcement workflows today.
- Bengaluru traffic police log ~298,450 violations over ~5 months — the
  data exists, but nobody's using it to predict *where it happens next*.
Speaker note: ground this in the real dataset, not a generic pitch.

### Slide 3 — Solution
Three questions answered: **Where** will violations cluster next 60
minutes (hotspot classifier)? **How severe** (count regression)? **What
should enforcement do** (rule-based recommendation engine)? End-to-end:
raw data → trained models → live API → dashboard.
Speaker note: emphasize this is a decision-support tool, not autonomous
enforcement — every recommendation is reviewable.

### Slide 4 — Constraint: Internal-Data-Only
No external maps, weather, traffic feeds, or road-network data anywhere in
the modeling pipeline (ADR-001) — only the 24 provided columns and what's
derived from them. External APIs power only the UI map tiles.
Speaker note: this is a deliberate constraint, not a limitation we ran into —
makes the model dependency-free at inference time.

### Slide 5 — Pipeline / Architecture
Insert `docs/architecture_diagram.png`.
Walk through: ingestion → feature engineering (H3, rolling, historical-risk) →
3-model comparison → hardening → risk/recommendation/alert layer → API → dashboard.
Speaker note: 6 phases, each with its own committed, tested deliverable —
not a one-shot build.

### Slide 6 — Modeling Results
| Model | Val PR-AUC | Test PR-AUC |
|---|---|---|
| **CatBoost (winner)** | **0.8767** | **0.8732** |
| LightGBM | 0.8649 | — |
| XGBoost | 0.8632 | — |

Time-based split (train on past, test on future) — never random.
Speaker note: this is the actual leaderboard, not cherry-picked.

### Slide 7 — Decision-Layer Hardening (the rigor slide)
- Cost-aware threshold: switched 0.30 → **0.15** (false negatives weighted 3x worse)
- Calibration tested (Platt/Isotonic) — **neither adopted**, didn't clear the bar
- **Spatial holdout: FAIL** (7.88% PR-AUC drop on unseen H3 cells) — disclosed, not hidden
- Reduced-spatial-identity check: removing `h3_cell` only costs 0.55% PR-AUC → kept it, froze the feature set
Speaker note: *this slide is the credibility slide* — show a real FAIL, explain why it doesn't block deployment within existing coverage.

### Slide 8 — Risk Engine + Recommendations + Alerts
`risk_score = 0.40×hotspot_prob + 0.30×predicted_count + 0.20×persistence + 0.10×recent_intensity`
→ LOW/MEDIUM/HIGH/CRITICAL (data-driven cutoffs, not round numbers) →
Monitor/Patrol/Deploy enforcement/Tow operation candidate (rule-based, no LLM) →
GREEN/YELLOW/ORANGE/RED alerts.
Speaker note: mention the real "No Junction" data quirk (49.5% of rows) and
how the rule engine explicitly excludes it from escalation logic — shows attention to data quality.

### Slide 9 — Dashboard
4 views: Live Risk Map (Leaflet), Forecast Panel, Operations View, Analytics
View. Reference `docs/screenshots/README.md` descriptions or live screenshots.
Speaker note: built in Next.js + Leaflet, talks to the live FastAPI backend,
no external predictive data in the map either.

### Slide 10 — Live Demo
3 real scenarios from `docs/demo_scenarios.md`: alert replay, hotspot growth
at Elite Junction (real night, 2023-12-23), and an escalation to "Tow
operation candidate" at Safina Plaza Junction. Run live or show captured output.
Speaker note: see `docs/demo_script.md` for the full narration.

### Slide 11 — Known Limitations (said out loud, not buried)
- Cold-start geography: won't generalize to brand-new H3 cells without retraining
- Missing enforcement timestamps: `closed_datetime` 100% missing in this extract
- No live streaming yet (Phase 7) — dashboard uses latest historical snapshot per cell
- Risk weights/thresholds are documented assumptions, not validated against real outcomes
Speaker note: judges trust honesty about limitations more than a claim of perfection.

### Slide 12 — Impact & Roadmap
Today: a working, tested, internally-consistent decision-support pipeline
(6 phases, ~100+ tests, every claim backed by a real number). Next: Phase 7
(real-time streaming via Kafka), Phase 8 (full dashboard polish), live
deployment to Render/Vercel (prepared, `docs/deployment.md`).
Speaker note: end on what's real and working today, not just what's planned.
