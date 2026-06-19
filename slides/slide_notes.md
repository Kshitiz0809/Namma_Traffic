# Slide Notes — Parking Intelligence + Predictive Alert Platform

Full slide outline: [`docs/ppt_outline.md`](../docs/ppt_outline.md)  
Demo script: [`docs/demo_script.md`](../docs/demo_script.md)

These notes give the *spoken* content for each slide — what to say, not just what's on screen.
Target runtime: 12-minute presentation + 3-minute demo + 5-minute Q&A.

---

## Slide 1 — Title

**On screen:** "Parking Intelligence + Predictive Alert Platform"  
Subtitle: Parking-Induced Congestion Risk Engine  
Your name, team, date

**Say:**
> "We built a system that tells traffic enforcement where to go *before* violations
> cluster, not after. Everything I'll show you is from a real dataset — 298,450
> Bengaluru traffic-police records. Real numbers. Real results. Including the
> results that weren't great."

---

## Slide 2 — Problem

**On screen:**
- 298,450 violations logged over ~5 months
- Enforcement today: reactive (ticket after violation)
- No system says: "this junction will be a hotspot in the next hour"

**Say:**
> "The data already exists. Bengaluru traffic police have been logging every
> parking violation for years — location, vehicle type, offence code, timestamp.
> But nobody's been using it predictively. Every dispatch decision today is based
> on what already happened, not what's about to happen. We changed that."

**Pause point:** let the 298,450 number land. It's real.

---

## Slide 3 — Solution

**On screen:** Three questions → three outputs  
Where (hotspot classifier) + How severe (count regression) + What to do (rule engine)

**Say:**
> "We answer three specific questions. First: will this zone become a hotspot
> in the next 60 minutes? That's a binary classification problem. Second: if
> so, how bad — how many violations to expect? That's a regression. Third: what
> should enforcement actually do about it? That's a rule-based recommendation
> engine — transparent, auditable, no black box."

**Key message:** this is a decision-support tool, not autonomous enforcement.
Every recommendation is reviewable.

---

## Slide 4 — Internal-Data-Only Constraint

**On screen:**
- 24 columns: coordinates, timestamps, vehicle, offence codes
- No external maps, weather, traffic feeds
- OpenStreetMap tiles: UI rendering only, zero influence on predictions

**Say:**
> "We made a deliberate architectural decision early: use only the 24 columns
> we were given. No weather API, no road-network graph, no third-party hotspot
> service. Why? Because it makes the model dependency-free at inference time.
> When new data arrives, you run the pipeline. Nothing else breaks."

**If asked:** mention ADR-001 in DECISIONS.md — this was a documented choice,
not something we ran into.

---

## Slide 5 — Pipeline / Architecture

**On screen:** [`docs/architecture_diagram.png`](../docs/architecture_diagram.png)

**Say:**
> "Six phases, each one a committed, tested deliverable. Raw CSV in at the top,
> predictions out at the bottom. The feature engineering layer is where the
> interesting work happens: H3 hexagonal spatial binning at 174-meter resolution,
> Hawkes-decay rolling intensity, leakage-safe historical-risk aggregations —
> all derived from the 24 raw columns, nothing external."

**Walk through left to right:** Ingestion → Features → Models → Decision layer
→ API → Dashboard.

**Key message:** every layer is independently tested. The model doesn't know
about the API; the API doesn't know about the frontend.

---

## Slide 6 — Modeling Results

**On screen:**

| Model | Val PR-AUC | Test PR-AUC |
|---|---|---|
| **CatBoost** | **0.8767** | **0.8732** |
| LightGBM | 0.8649 | — |
| XGBoost | 0.8632 | — |

Time-based split. Test touched exactly once.

**Say:**
> "We ran three models. CatBoost won — highest PR-AUC, best calibration, and it
> handles the 2,534 distinct H3 cell categories natively without manual encoding.
> The val/test scores are nearly identical: 0.8767 vs 0.8732. That gap is small
> enough that we're not overfitting to the validation set. The test number is the
> one that matters, and we only looked at it once."

**If asked about 'why not a neural network':** tree ensembles outperform on
tabular data at this scale — there's nothing here that needs sequence modeling
or image features.

---

## Slide 7 — Decision-Layer Hardening (Credibility Slide)

**On screen:**
- Cost threshold: 0.30 → **0.15** (FN 3× worse than FP)
- Calibration: tested, **rejected** (didn't clear the bar)
- **Spatial holdout: FAIL** — 7.88% PR-AUC drop on unseen H3 cells
- Remove `h3_cell` entirely: only 0.55% drop → feature kept; set frozen

**Say:**
> "This is the most important slide. We didn't stop at 'it scored well' — we
> stress-tested it. We checked: does it generalize to locations it's never seen?
> No — a 7.88% accuracy drop on unseen H3 cells. We're telling you that. We
> checked: can we improve calibration? We tried Platt and Isotonic scaling —
> neither cleared our 5% Brier improvement bar, so we kept the baseline. Every
> one of these results is in the docs, with the exact numbers and the exact
> decision."

**Key message:** judges trust a disclosed FAIL more than a claim of perfection.
This is the slide that shows rigor.

---

## Slide 8 — Risk Engine + Recommendations + Alerts

**On screen:**
```
risk_score = 0.40×hotspot_prob + 0.30×predicted_count
           + 0.20×persistence + 0.10×recent_intensity
```
→ LOW/MEDIUM/HIGH/CRITICAL (data-driven band cutoffs: 34.0/45.1/54.2)  
→ Monitor / Patrol / Deploy enforcement / Tow operation candidate  
→ GREEN / YELLOW / ORANGE / RED alerts

**Say:**
> "The risk score is a derived signal — not a new ML target, just a weighted
> combination of what the models already produce. The band cutoffs aren't round
> numbers: 34, 45, 54. Those came from the actual percentile distribution of
> the score — if we'd used 40/60/80, the CRITICAL band would have been empty.
> The recommendation engine is pure rules — you can read the YAML file that
> drives it. No LLM, no learned policy, nothing you can't audit."

**Mention the "No Junction" quirk:** 49.5% of rows have `junction_name == "No
Junction"` — a data placeholder. The escalation rules explicitly exclude it.
That's the kind of data-quality detail that's easy to miss and important to catch.

---

## Slide 9 — Dashboard

**On screen:** screenshot or live dashboard  
Four views: Live Risk Map / Forecast Panel / Operations View / Analytics View

**Say:**
> "The dashboard is built in Next.js and Leaflet. Every prediction on the map
> comes from our API — the OpenStreetMap tiles are just for rendering context.
> The Forecast Panel lets you look up any H3 cell, including ones the model
> has never seen — in which case it tells you that explicitly rather than making
> something up. The Operations View is the thing a real dispatcher would use:
> a sorted queue of alerts, filterable by severity level."

---

## Slide 10 — Live Demo

**On screen:** terminal + browser

**Say:**
> "Let me show you three real scenarios — not synthetic data, actual records from
> the dataset." [See `docs/demo_script.md` for full narration]

**Scenario 1:** Alert replay — `python -m app.models.demo_seed alerts`  
**Scenario 2:** Hotspot growth at Elite Junction (2023-12-23)  
**Scenario 3:** MAXI-CAB escalation to "Tow operation candidate" at Safina Plaza

**Fallback if demo breaks:** show `docs/alerts.json` and walk through the
top-3 alerts manually. The numbers are all real.

---

## Slide 11 — Known Limitations

**On screen:**
- Cold-start: won't generalize to brand-new H3 cells
- `closed_datetime` 100% missing — resolution time uncomputable
- No live streaming — snapshot, not real-time
- Risk weights are stated assumptions, not validated against real outcomes

**Say:**
> "We're saying these out loud, not burying them in an appendix. A model that
> claims to have no limitations isn't being honest — it's hiding things. These
> four are the real ones. The most important is the cold-start issue: if
> Bengaluru traffic police open a new enforcement zone tomorrow, our model has
> no history for it. We handle that gracefully — the API says 'no data,
> here's a conservative default' — but it can't predict what it's never seen."

---

## Slide 12 — Impact + Roadmap

**On screen:**
- Today: working, tested, internally consistent decision-support pipeline
- 58 tests passing across 6 phases
- Every claim backed by a real number
- Next: Kafka streaming → live features; expanded coverage → fix cold-start

**Say:**
> "What we have today is something you can actually run. Clone the repo, provide
> the dataset, run five commands, and you get a live dashboard with real
> predictions. The roadmap items aren't wishful thinking — the infrastructure
> is already prepared. Kafka config is in the .env template. Render and Vercel
> configs are committed. The next phase is connecting the plumbing, not
> redesigning the system."

**Close:**
> "Six phases, 58 tests, every limitation disclosed. Thank you."

---

## Assets Checklist

| Asset | Location | Status |
|---|---|---|
| Architecture diagram | [`docs/architecture_diagram.png`](../docs/architecture_diagram.png) | ✅ Generated (Phase 6) |
| System flow diagram | [`docs/system_flow.png`](../docs/system_flow.png) | ✅ Generated (Phase 6) |
| Model leaderboard table | [`docs/leaderboard.csv`](../docs/leaderboard.csv) | ✅ Real results |
| Calibration curve | [`docs/calibration_curve.png`](../docs/calibration_curve.png) | ✅ Generated (Phase 3.5) |
| Threshold curve | [`docs/threshold_curve.png`](../docs/threshold_curve.png) | ✅ Generated (Phase 3.5) |
| Forecast curves | [`docs/forecast_curves.png`](../docs/forecast_curves.png) | ✅ Generated (Phase 3.5) |
| SHAP summary | [`docs/shap_summary.png`](../docs/shap_summary.png) | ✅ Generated (Phase 3.5) |
| Risk examples | [`docs/alerts.json`](../docs/alerts.json) | ✅ 60 real alerts |
| Dashboard screenshots | [`docs/screenshots/README.md`](../docs/screenshots/README.md) | ⚠ Described, not captured |

**Screenshot plan for live capture (now that disk space is recovered):**
1. Open `http://localhost:3000` (Live Risk Map)
2. Screenshot — save as `slides/assets/screenshot_risk_map.png`
3. Click Forecast Panel, enter cell `89618925c03ffff`
4. Screenshot — save as `slides/assets/screenshot_forecast.png`
5. Click Operations View — sort by risk descending
6. Screenshot — save as `slides/assets/screenshot_operations.png`
7. Click Analytics View — model comparison chart
8. Screenshot — save as `slides/assets/screenshot_analytics.png`

Recommended resolution: 1440×900 or 1280×800.
