# Screenshots

**Real browser screenshots were skipped this round** — the environment hit
a disk-space wall (~206MB free) while installing a headless Chromium for
Playwright, and you opted to skip rather than wait/free space. Disk space
has since recovered (~6GB free at last check), so re-running the capture is
straightforward whenever you want real screenshots:

```bash
# Terminal 1
cd backend && uvicorn app.main:app --port 8000
# Terminal 2
cd frontend && npm run dev
# Terminal 3
cd frontend && npx playwright install chromium && node screenshot.js  # see git history for screenshot.js, or recreate similarly
```

In the meantime, here is exactly what each view looks like (verified by
actually running the dashboard locally and reading its rendered output/API
responses — just not photographed):

## 01 — Live Risk Map
Full-width Leaflet map centered on Bengaluru (12.9716, 77.5946), zoom 12,
OpenStreetMap tiles. Colored circle markers per H3 cell: green (LOW, hidden
by default), yellow (MEDIUM), orange (HIGH), red (CRITICAL). A "minimum risk
band" filter row above the map (LOW/MEDIUM/HIGH/CRITICAL buttons) and a
zone-count indicator. Clicking a marker opens a popup with junction name,
zone ID, alert level, probability, risk score, and recommendation. Legend
row below the map.

## 02 — Forecast Panel
A form: H3 cell ID text input, 3 quick-select example buttons (Safina Plaza
area, Elite Junction area, "Unknown cell (cold start demo)"), an optional
vehicle-type override text input, and a "Get forecast" button. Below, a
color-coded result card (green/yellow/orange/red border matching risk band)
showing hotspot probability, predicted count, congestion risk, confidence,
risk band, recommendation, and the top-2 contributing factors as a list.
Cold-start zones show a distinct "no historical data" message instead.

## 03 — Operations View
Top: a 4-5 card grid showing intervention counts (Monitor/Patrol/Deploy
enforcement/Tow operation candidate) plus an "Escalated by rule engine"
count. Below: a sortable-by-risk alert queue table with columns Level
(colored badge), Junction, Risk score, Probability, Recommendation, Escalated.

## 04 — Analytics View
A pie chart of the live risk-band distribution (LOW/MEDIUM/HIGH/CRITICAL,
colored to match the alert palette), a bar chart comparing CatBoost/
LightGBM/XGBoost validation PR-AUC (CatBoost winning), and a 4-card stat
row: operating threshold (0.15), operational horizon (60 min), spatial
holdout verdict (FAIL, shown in a red-tinted card), spatial abstraction
verdict (PASS). A footer line states the feature set is frozen and data
sources are internal-only.

---

For the PPT (`docs/ppt_outline.md`), use `docs/architecture_diagram.png`
and `docs/system_flow.png` (both real, generated) for the architecture
slides, and the descriptions above (or live screenshots, once captured)
for the product slides.
