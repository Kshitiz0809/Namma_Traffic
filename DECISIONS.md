# Architecture Decisions

Running log of non-obvious design choices, why they were made, and what
alternatives were considered. Updated every phase.

---

## ADR-001: No external data, ever — internal-only feature engineering

**Decision:** Every feature must be derivable from the 24 provided columns
alone. No map enrichment, road network data, weather, events, demographics,
or external labels — at any phase, not just Phase 2.

**Why:** Stated hard constraint. It also has a real benefit for a hackathon
demo: a model trained only on internal data has no external API dependency
at inference time, so it can't silently degrade if a third-party API rate-limits
or goes down during judging.

**What's still allowed:** External APIs may power the *deployment/UI* layer
(e.g., Leaflet base map tiles in Phase 8) — never predictions or training data.

**Alternatives considered:** OSM road-network distance-to-junction features,
weather features (rain → more illegal parking near doors). Rejected — not
because they wouldn't help, but because they're out of scope by constraint.

---

## ADR-002: H3 over GeoHash as the primary spatial index

**Decision:** Use Uber's H3 hexagonal grid (`h3` Python package, v4 API) as
the primary spatial key. GeoHash is computed too (`geohash` column) for
comparison/familiarity but H3 is what features and models key off.

**Why H3 over GeoHash:**
- H3 cells are roughly equal-area hexagons; GeoHash cells are rectangles whose
  width/height ratio distorts with latitude (worse the further from the
  equator — Bengaluru is at 13°N, not huge but non-zero distortion).
- Hexagons have uniform adjacency (6 equidistant neighbors) — GeoHash
  rectangles have edge-neighbors and corner-neighbors at different distances,
  which complicates any future neighbor-aggregation or graph features
  (relevant if ST-GCN is ever revisited).
- H3 has built-in multi-resolution hierarchy (`h3.cell_to_parent` /
  `h3.cell_to_children`), useful for "junction density" / "police_station
  density" style rollups at different granularities without re-binning by hand.

**Resolution chosen:** H3 resolution 9 (edge length ≈ 174m, area ≈ 0.1 km²).
Chosen by checking the median nearest-neighbor distance between violation
points in the dataset — res 9 gives enough cells to discriminate hotspots
without making most cells single-occupancy. Resolution is a named constant
(`H3_RESOLUTION` in `backend/app/features/spatial.py`) — trivial to change
and re-run if Phase 3 model results suggest otherwise.

**Alternatives considered:** DBSCAN/KMeans spatial clustering (data-dependent
cluster shapes, unstable across retrains as new data arrives — rejected for
a system meant to score new incoming violations against a stable grid).

---

## ADR-003: Parquet as the interchange format between pipeline stages

**Decision:** `data/processed/*.parquet`, not CSV, for every pipeline output.

**Why:** Preserves dtypes (esp. datetime64, nullable Int) round-trip, which
CSV doesn't; columnar reads are faster for the column-heavy feature tables
this phase produces; ~5-10x smaller on disk than CSV for this dataset shape.
Postgres load (mentioned in original infra plan) is deferred until an API
actually needs row-level transactional access — until then parquet is simpler
and the modular pipeline doesn't need a database in the loop.

---

## ADR-004: Modular pipeline layout

**Decision:**
```
backend/app/
  ingestion/   - load + validate raw CSV (Phase 1)
  features/    - spatial.py, temporal.py, operational.py, rolling.py,
                 aggregated.py, outliers.py, targets.py, build_features.py
  models/      - empty stub now, filled in Phase 3 (CatBoost/LightGBM/XGBoost)
  serving/     - empty stub now, filled in Phase 8 (FastAPI prediction endpoints)
```
Each stage reads the previous stage's parquet output and writes its own —
no stage reaches backwards into raw CSVs or forward into stages that don't
exist yet. This is what makes "rebuild only what changed" possible and keeps
the diff for each phase reviewable.

**`targets.py` is deliberately separate from the other feature modules.**
Targets are allowed to look at *future* data (that's the entire point of a
supervised label); features are never allowed to. Keeping them in one file
that nothing else imports from makes it mechanically impossible to
accidentally join a target column into the feature matrix.

---

## ADR-005: Target variable definition (for Phase 3/4 modeling)

**Decision:** Define targets now, at the row level, as **forward-looking
windowed counts in the same H3 cell**:

- `target_count_15m`, `target_count_30m`, `target_count_60m` — count of
  other violations in the same `h3_cell` within the next 15/30/60 minutes
  after this row's `created_datetime`.
- `target_hotspot_60m` — binary, `1` if `target_count_60m > 0`.

**Why this shape (vs. a global per-cell static "hotspot score"):**
- It directly matches Phase 4's stated forecast horizons (15/30/60 min), so
  one target-construction step serves both the Phase 3 spatial classifier
  and the Phase 4 temporal forecaster — same label, different framing
  (classification vs. regression on the same `target_count_60m` column).
- It's *row-conditioned* (depends on the actual event and its real
  timestamp/location), not a static per-cell average — closer to "given a
  violation just happened here, how hot is this cell right now" than "is
  this cell historically bad", which is more useful for a real-time alert
  engine.
- Computing it only requires `h3_cell` + `created_datetime`, both internal.

**Leakage note:** these columns must NEVER be joined into a training feature
matrix — they're written to a separate `targets_*.parquet`, not the main
`features_*.parquet`, and `feature_dictionary.md` flags them explicitly.

**Alternative considered:** a static `is_hotspot` label per (h3_cell, day)
computed from the full-period count, thresholded at a quantile. Rejected as
the *primary* target — it doesn't vary with time-of-day/intervention, so a
model trained on it can't feed a real-time alert engine. May still be useful
as a secondary descriptive feature in EDA, not as the model target.

---

## ADR-006: Leakage-safe historical aggregation pattern

**Decision:** Every "historical risk" / rolling feature is computed by
sorting on `created_datetime` ascending and using only **strictly prior**
rows — implemented with pandas time-based `.rolling(window, closed='left')`
for fixed windows, and `groupby(...).cumcount()` / expanding sums for
unbounded historical aggregates (junction risk, offence risk, etc.).
`closed='left'` excludes the current row itself from its own window, so a
violation never gets to "see itself" in its own historical-risk feature.

**Why this matters enough to call out:** target leakage via "future" or
"self" information is the single most common way a hackathon model looks
great in offline eval and is useless live. Every feature module has a
docstring stating its leakage guarantee; `ml/notebooks/03_feature_validation.ipynb`
includes an explicit check that re-derives a sample of rolling features by
brute-force filtering and confirms they match the vectorized implementation.

---

## ADR-007: Outliers are flagged, not dropped

**Decision:** `is_outlier_coordinate` (bool) added for rows outside the
Bengaluru bounding box (see Phase 1 schema check — 168 rows). Rows are kept
in the dataset; nothing is deleted at the feature-engineering stage.

**Why:** Per explicit instruction — compare model performance with/without
before deciding. Also, "outside bounding box" might mean "bad GPS fix" or
might mean "legitimate edge-of-jurisdiction violation" — dropping silently
forecloses that distinction before anyone's looked at it.

---

## ADR-008: Modeling direction (recorded now, executed Phase 3+)

**Decision:** Phase 3 builds baselines in this order: **CatBoost → LightGBM
→ XGBoost**, compared on the same train/val/test split and feature set, with
the best performer carried forward. ST-GCN, graph pipelines, and complex
ensembles are deferred unless baseline metrics show a gap that justifies the
added complexity (and the added complexity *risk* — graph models are much
harder to debug under hackathon time pressure).

**Why CatBoost first:** native categorical handling (vehicle_type, junction_name,
police_station, center_code are all categorical) without manual encoding,
which is a reasonable first baseline with the least feature-prep surface
area for bugs to hide in. LightGBM/XGBoost follow with the same engineered
features (one-hot/target-encoded as needed) for a fair comparison.

**Explainability:** SHAP added in Phase 3 scope (not Phase 2) since it
explains a trained model, not a feature table.

---

## ADR-009: Live-availability exclusion — administrative/post-hoc columns are not model features

**Decision:** `validation_status`, `validation_delay_minutes`,
`enforcement_delay_minutes`, `resolution_time_minutes`, and
`data_sent_to_scita` are excluded from the **model feature set**, even
though they passed ADR-006's temporal leakage-safety check (they don't use
future *rows*, just this row's own delayed fields).

**Why this is a different kind of leakage than ADR-006 covers:** ADR-006
guards against seeing future *events*. This guards against seeing future
*knowledge about the current event*. `validation_status` is decided by a
human reviewer, often days after `created_datetime` (audit: ~58% of rows
still have a null `validation_timestamp`, meaning many cases sit unreviewed
for a long time). A live alert system predicting "will this cell be a
hotspot in the next 60 minutes" must fire on information available **at
`created_datetime`** — it cannot wait for a review that hasn't happened yet.
Including these columns would make offline metrics look better (the model
partially learns "rejected/duplicate records correlate with different
future patterns") in a way that's impossible to replicate in production.

**What's still allowed:** these columns remain in `features.parquet`
(nothing is deleted, per the general "flag don't drop" philosophy) and are
used for descriptive/audit purposes — just excluded from `MODEL_FEATURE_COLUMNS`
in `backend/app/models/feature_set.py`.

---

## ADR-010: Time-based split — train (earliest) / validation (middle) / test (latest)

**Decision:** Split `features.parquet` by `created_datetime` into three
contiguous, non-overlapping blocks: train = earliest 70%, validation = next
15%, test = latest 15% (by row count after time-sorting, not by calendar
date, so each split has a comparable sample size given uneven monthly
volume — see `docs/data_quality_report.md`).

**Why not random k-fold:** every leakage-safe rolling/historical feature
(ADR-006) is still *time-correlated* — `hotspot_frequency` for a row in
March implicitly reflects accumulated November-February activity. A random
split would put temporally-adjacent rows (same cell, minutes apart) in both
train and test, letting the model effectively memorize near-duplicate
contexts rather than generalize. Time-based splitting is the only split
that honestly simulates "train on the past, predict the future."

**Consequence accepted:** the test set's class balance / feature
distributions can differ from train's (e.g., if violations trend up over
the months) — that's realistic, not a bug, and is reported rather than
corrected for.

---

## ADR-011: Congestion score is a derived/reported metric, not a training target (yet)

**Decision:** `congestion_score = 0.5×normalized_violation_count +
0.3×hotspot_persistence + 0.2×enforcement_density` is computed in
`backend/app/models/congestion_score.py` as a **descriptive output**, using
only features already validated in Phase 2. It is NOT used as a model
training target in Phase 3.

**Component mapping (all internal, all leakage-safe):**
- `normalized_violation_count` = `violation_density`, min-max scaled using
  statistics fit on the **train split only** (scaling on val/test stats
  would leak their distribution back into a score meant to generalize).
- `hotspot_persistence` = `rolling_hotspot_intensity`, same train-fit scaling.
- `enforcement_density` = `police_station_density`, same train-fit scaling.

**Why not train on it directly yet:** it's a hand-weighted linear
combination, not a ground-truth label — training a model to predict your
own formula just re-learns the formula's algebra, not anything about real
congestion outcomes. It's reported now so Phase 5 (Parking-Induced Congestion Risk Engine —
renamed from "Congestion Impact Engine" per Phase 5 review: the system
estimates operational risk derived from parking behavior, not measured
traffic congestion)
has a validated, documented starting formula; if Phase 5 needs a *learned*
congestion score, that's a new ground-truth-label discussion, not a reuse
of this one.

---

## ADR-012: Required ablation experiments (A-D) run on the winning baseline classifier

**Decision:** four single-factor ablations, each comparing "with" vs
"without" against the same baseline configuration, all measured on the
*same* time-based validation split for comparability:
- **A.** with vs without `is_outlier_coordinate` rows (168 rows)
- **B.** with vs without `is_duplicate_vehicle_event` rows (9,521 rows)
- **C.** H3-derived features vs GeoHash-derived features as the spatial key
- **D.** raw counts (`hotspot_frequency` only) vs full rolling feature set
  (`violations_last_15/30/60m`, `same_hour_previous_day`, `rolling_hotspot_intensity`)

Each is a single-factor change so the effect is attributable — running all
4 togglable choices as a full 2⁴ grid (16 runs) would cost more compute for
marginal extra insight at this stage; if two factors show a surprising
interaction, that's a candidate follow-up, not a default.

---

## ADR-013: Model feature set excludes free-text and high-cardinality identifier columns

**Decision:** `location` (free-text address string), `vehicle_number`,
`updated_vehicle_number`, `device_id`, `created_by_id` are excluded from
`MODEL_FEATURE_COLUMNS`. `h3_cell`, `junction_name`, `police_station`,
`center_code`, `vehicle_type`, `primary_offence_code`, `primary_violation_type`
are kept as categorical features (cardinalities 17-2,534 — see
`backend/app/models/feature_set.py` for the exact list and counts).

**Why:** free-text/raw-identifier columns either have no usable structure
for a tree model (`location` would need NLP, out of scope) or are
near-unique-per-row identifiers that a tree model would overfit to as a
memorization shortcut (`vehicle_number`, `device_id`) rather than learning
generalizable patterns.

---

## ADR-014: Cost-aware threshold replaces F1-only operating point

**Decision:** Phase 3.5 introduces an explicit cost model —
`cost = FP * cost_fp + FN * cost_fn`, default `cost_fp=1, cost_fn=3` — and
sweeps thresholds 0.05-0.95 (step 0.05) computing precision, recall, F1,
specificity, FPR, and cost at each. Three named operating points are
reported (`backend/app/models/threshold_optimization.py`,
`docs/threshold_selection.md`): F1-optimal (Phase 3's original criterion,
kept for comparison), high-precision (lowest cost among thresholds with
precision ≥0.85, for patrol-capacity-constrained deployments), and balanced
(minimizes total cost directly — the new recommended default).

**Why 3x weight on false negatives:** a missed hotspot means an enforcement
opportunity is lost entirely; a false positive means a patrol checks a
location that turns out fine — wasteful, but recoverable. This 3:1 ratio is
a **stated assumption**, not measured from real cost data (none was
provided). Phase 6 (Alert Engine) should replace it with actual
intervention-cost figures if/when available; until then it's a documented
placeholder, not a tuned constant.

**Why not just maximize F1:** F1 treats false positives and false negatives
as equally costly, which is rarely true for a real intervention system and
isn't even claimed to be true here — it was Phase 3's metric because no
explicit cost model existed yet, not because it's the right deployment criterion.

---

## ADR-015: Test-set reuse policy for hardening diagnostics

**Decision:** Phase 3 established "test is touched exactly once, with the
already-chosen winner." Phase 3.5's hardening tasks (calibration evaluation,
threshold sweep) read test-set predictions multiple times across different
diagnostics. This is **read-only reuse for evaluation, not re-selection** —
no hardening task result feeds back into choosing a different base model or
retraining with test-set knowledge. The original Phase 3 model-selection
decision (CatBoost, chosen on validation PR-AUC) is never revisited based on
what these diagnostics find on test.

**Why this is still safe:** the distinction that matters is between "using
test to choose/tune" (which leaks evaluation-set information into the
model) and "using test to characterize an already-fixed model" (calibration
quality, threshold trade-offs) — the latter doesn't change what was
trained, only how its frozen outputs get post-processed/interpreted, so
reusing the fixed test set for several independent characterizations of the
same frozen model doesn't compound leakage the way repeated model-selection
peeking would.

---

## ADR-016: Spatial holdout methodology and result

**Decision:** H3 cells (not rows) are split 80/20 into train-cells/holdout-cells
(`backend/app/models/spatial_holdout.py`, seed=42). CatBoost is retrained
using only train-period rows from train-cells, then evaluated on the SAME
validation time window, split by whether each row's cell was seen during
training — isolating the spatial effect from the temporal one (both
evaluation sets share the same time period).

**Result: FAIL.** PR-AUC drops 7.88% on unseen cells (0.8833 seen vs 0.8137
unseen) — above the 5% acceptance bar. This is consistent with the SHAP
audit (ADR-017): `h3_cell` has mean rank 1.0 across bootstraps, i.e. it is
*always* the single most important feature, never displaced. **The model
partially memorizes per-cell identity rather than purely generalizing from
cell-agnostic signals.**

**What this does and doesn't mean:** it does NOT mean the model is useless
for its actual deployment context — Bengaluru's H3 grid is fixed, and most
real future predictions will fall in cells the model has already seen
historical data for. It DOES mean the model should not be trusted to
generalize to genuinely new geographic coverage areas without retraining,
and that `h3_cell`'s outsized influence is a known, documented risk rather
than an assumed strength. Full writeup + recommendations: `docs/spatial_holdout.md`.

---

## ADR-017: SHAP stability audit methodology and findings

**Decision:** SHAP values recomputed across 5 bootstrap resamples (50% of
validation set each, `backend/app/models/shap_audit.py`) to check whether
the top-feature ranking is a stable property of the model or an artifact of
one particular sample. Explicitly checked for: H3 dominance, timestamp
leakage (verified `created_datetime` and other raw timestamp columns are
never in `MODEL_FEATURE_COLUMNS` — confirmed absent), target proxies
(numeric features with |correlation| ≥0.95 to the target — none found; the
strongest engineered features top out around 0.3-0.4, consistent with
Phase 2's feature validation notebook).

**Findings:**
- **Top-10 feature ranking is perfectly stable** (Jaccard stability score =
  1.0 — the exact same 10 features appear in every bootstrap's top-10, just
  reordered slightly within that set).
- **H3 dominance confirmed**: `h3_cell` has mean rank 1.0 across all 5
  bootstraps (always #1) — corroborates the spatial holdout failure (ADR-016)
  from an independent angle (explainability vs. held-out accuracy), which is
  more convincing than either result alone.
- No timestamp leakage, no target proxies detected.

Full table: `docs/feature_stability.csv`. Plot: `docs/shap_summary.png`.

---

## ADR-018: Multi-horizon comparison — raw PR-AUC is not comparable across horizons

**Decision:** `target_hotspot_15m/30m/60m/90m` all added to `targets.parquet`
(extending `TARGET_WINDOWS_MINUTES` in `backend/app/features/targets.py`).
CatBoost retrained per horizon on the same time-based split; results in
`docs/horizon_comparison.csv`.

**Critical finding — raw PR-AUC rises with horizon length (0.7834 → 0.8929
from 15m to 90m) almost entirely because longer windows have a higher
positive rate (60.5% → 72.4%)**, not because longer-horizon predictions are
inherently better. A trivial "always predict positive" classifier would
also score better PR-AUC at a higher base rate. Reporting raw PR-AUC across
horizons without this caveat would be actively misleading.

**Fix:** `lift_over_base_rate = PR-AUC / positive_rate` as a crude
base-rate-normalized comparison (a random/always-positive classifier scores
lift ≈1.0; higher means genuine skill above the trivial baseline). By this
corrected metric, **shorter horizons actually have higher lift** (15m:
1.294 vs 90m: 1.234) — the opposite conclusion from reading raw PR-AUC alone.

**Recommendation:** see `docs/horizon_comparison.csv`/`MODEL_REPORT.md` for
the final operational horizon choice — made using lift, not raw PR-AUC.

---

## ADR-019: Reduced-spatial-identity experiment — PASS, h3_cell kept, feature set frozen

**Decision:** Final robustness check before feature lock. Model A (existing
Phase 3 winner, not retrained) vs. Model B (ONE new training run with
`h3_cell`/`geohash` removed from categorical features, everything else —
density, rolling, temporal, aggregated-historical, and organizational
categoricals like `junction_name`/`police_station` — unchanged). Result:
**PR-AUC drop of only 0.55%** (0.8767 → 0.8719) on the same validation set.
**Verdict: Spatial abstraction = PASS** (≤3% acceptance bar).

**This does not contradict ADR-016's spatial-holdout FAIL.** The two
experiments measure different things:
- ADR-016 (spatial holdout): performance on cells **never seen at all**
  during training — fails because almost every per-cell feature
  (identity-based or not) starts cold for a genuinely new location.
- ADR-019 (this experiment): marginal value of the **raw `h3_cell` ID
  column itself**, for cells already seen — passes because that identity
  information is largely redundant with the density/rolling/historical-risk
  features and organizational categoricals already present.

**Combined picture:** the model's spatial fragility is a cold-start problem
affecting most historical-aggregate features broadly, not a dependency on
`h3_cell`'s raw identity specifically. Full writeup: `docs/spatial_dependency.md`.

**Decision: keep `h3_cell`.** Removing it buys negligible robustness (the
cold-start issue isn't fixed by dropping it — untested here per the explicit
"no additional variants" instruction, but reasoned through in the writeup)
while giving up real accuracy (0.55%, plus the threshold shift from 0.30→0.35
in Model B). Per explicit instruction, this result does NOT block deployment.

**FEATURE SET IS NOW FROZEN.** No further feature additions/removals planned
without revisiting this ADR explicitly. `MODEL_FEATURE_COLUMNS` (NUMERIC_FEATURES
+ CATEGORICAL_FEATURES in `backend/app/models/feature_set.py`) is the locked
contract Phase 5+ builds on.

---

## ADR-020: Phase 5 — Parking-Induced Congestion Risk Engine

**Renamed from "Congestion Impact Engine"** per explicit review feedback:
the system estimates operational risk derived from parking VIOLATION
behavior, not measured traffic congestion — the old name overclaimed what
the data and models actually support.

**Decision: `risk_score` is a derived score, NOT a new ML target** (explicit
instruction). Computed from the FROZEN Phase 3 model outputs (classifier +
regressor, neither retrained) plus existing leakage-safe features:

```
risk_score = 100 * (0.40*hotspot_probability + 0.30*normalized_predicted_count
                   + 0.20*persistence + 0.10*recent_intensity)
```

Full derivation, normalization, and band-threshold reasoning:
`docs/risk_definition.md`. Notably, **fixed 40/60/80 band cutoffs were tried
first and rejected** — they left the CRITICAL band almost empty since the
real score distribution tops out around 65-82, not 100 (the 4 components
rarely all peak simultaneously). Replaced with train-period-fit percentile
cutoffs (34.0/45.1/54.2), which is the same "fit scaling on train only"
discipline as ADR-011's `congestion_score` and ADR-005's leakage-safety norms.

**Decision: recommendation engine is rule-based YAML, no LLM** (explicit
instruction). `docs/recommendation_rules.yaml` + `backend/app/models/recommendation.py`.
Found and worked around a real data quirk while building this: `junction_name
== "No Junction"` accounts for ~49.5% of all rows, which inflates that
category's `junction_historical_risk` to ~0.5 — not a genuine concentration
signal. The junction-history escalation rule explicitly excludes that
category and calibrates its threshold (0.05) against the NAMED-junction-only
distribution (median 0.013, 90th pct 0.051), not the contaminated full population.

**Decision: alert layer maps risk bands to colors 1:1** (LOW→GREEN,
MEDIUM→YELLOW, HIGH→ORANGE, CRITICAL→RED) using the FINAL (post-escalation)
band, not the raw pre-escalation band — an alert should reflect what the
recommendation engine actually decided, not an intermediate state.
"Top contributing factors" are read off the risk_score's own weighted
component contributions (cheap, directly tied to that score) rather than
recomputing SHAP per alert (would require per-row SHAP at alert-generation
time — disproportionate cost for a derived, non-ML-trained score).

**Decision: forecast service approximates "current state" from the latest
historical snapshot per H3 cell**, since no live streaming pipeline exists
yet (Phase 7). `hour`/`weekday`/cyclic-time features ARE recomputed against
the real current timestamp at request time; density/rolling/historical-risk
features are frozen at the last known event for that cell. This is a
documented approximation (see `backend/app/serving/forecast_service.py`
docstring), not a claim of real-time accuracy. Cold-start cells (no
historical data) get a conservative default response, not a fabricated
prediction — consistent with ADR-016's spatial-holdout finding.

**Two bugs found and fixed while building the forecast service:**
1. `_latest_by_cell.set_index("h3_cell")` silently dropped `h3_cell` from
   the row's own columns, breaking feature-vector construction for every
   known-cell request. Fixed by restoring it onto the row after lookup.
2. A full `sort_values()` + `groupby().tail(1)` on the 298k-row features
   table triggered a memory allocation failure in one execution context.
   Replaced with `groupby().idxmax()` (one pass, no full-table sort).

### Known limitations carried forward (explicit Task 6 requirement)
- **Cold-start geography**: confirmed by ADR-016 (spatial holdout FAIL,
  7.88% PR-AUC drop on unseen H3 cells) — the forecast service's cold-start
  path returns a conservative default rather than a number it can't stand behind.
- **Missing enforcement timestamps**: `closed_datetime` and
  `action_taken_timestamp` are 100% missing in this dataset (Phase 2 audit)
  — `resolution_time_minutes` carries no signal; the risk/recommendation
  engines never depend on it.
- **Internal-data-only constraint** (ADR-001) holds throughout Phase 5 —
  `risk_score`, `recommendation_rules.yaml`, and `forecast_service.py` use
  only the frozen models' outputs and existing engineered features. No
  external vehicle-size database, road-network data, or traffic feed of any
  kind was introduced for the vehicle-mix or junction-history logic.

---

## ADR-021: Phase 6 — Productization + Visualization

**Decision: Next.js + Leaflet dashboard, 4 views, talking only to the
already-frozen backend.** No model logic in the frontend — every number
the dashboard shows comes from `/forecast`, `/alerts`, or `/metrics`. CORS
opened (`allow_origins=["*"]`) since there's no auth/user-account system to
protect and the deployed frontend origin isn't fixed in advance — explicitly
flagged in `docs/api_contract.md` as a demo-appropriate choice to tighten later.

**Decision: `/alerts` and `/metrics` compute a live snapshot, not a cached
historical file.** `backend/app/serving/risk_snapshot.py` evaluates ALL
2,534 known H3 cells' latest historical event through the frozen models on
each process's first request, cached for the process lifetime. This
produces a meaningfully different (much lower-risk) distribution than
Phase 5's per-event validation sample (97% LOW vs. 58% LOW) — documented
explicitly in `docs/api_contract.md` as expected, not a discrepancy: a
single per-cell snapshot is calmer than a multi-event mix by construction.

**Decision: deployment is prepare-only, not executed.** No Render/Vercel
account credentials were available in this environment. `docker build` was
not run end-to-end (disk-space constraint at authoring time — see below).
`docs/deployment.md` documents the required pre-deploy step explicitly:
the gitignored model/data artifacts must be regenerated locally before
building the deploy image, since they aren't committed to the repo.

**Decision: demo_seed.py replays REAL historical sequences, never
synthetic/fabricated data.** Three scenarios, each anchored on a specific,
verified real example (not "first match" or arbitrary picks): a hotspot
growth surge at Elite Junction (2023-12-23, real timestamps), and a
HIGH→CRITICAL escalation at Safina Plaza Junction (2024-02-23 03:35:46,
a real MAXI-CAB violation). `docs/demo_scenarios.md` documents exactly how
each example was found, so it's reproducible, not hand-tuned for effect.

**Environmental constraint encountered and disclosed, not hidden:** this
execution environment hit a hard disk-space wall (~206MB free) partway
through Phase 6, causing a Chromium download (for screenshot automation)
to fail with `ENOSPC`, and twice causing intermittent
`numpy._core._exceptions._ArrayMemoryError` failures on routine
`pd.read_parquet`/`sort_values` calls that succeeded cleanly on retry.
Per explicit user decision, live browser screenshots were skipped this
round (`docs/screenshots/README.md` documents each view's appearance in
detail instead) rather than worked around at the cost of more disk churn.
Space later recovered to ~6GB free — re-capturing real screenshots is a
quick follow-up if desired, not a blocked task.

---

## ADR-022: Revisits ADR-019 — `h3_cell`/`geohash` dropped as model inputs, neighbor-averaged features added

**Context for revisiting a "frozen" decision:** ADR-019 explicitly froze the
feature set assuming a one-time training run. That assumption no longer
holds — ADR-024 adds a retraining pipeline so the model is expected to be
retrained periodically on new police-uploaded data, which can include
genuinely new H3 cells. ADR-019's own reasoning already flagged this exact
gap: *"the cold-start issue isn't fixed by dropping [h3_cell] — untested
here per the explicit 'no additional variants' instruction."* This ADR is
that untested variant, now that the constraint motivating it (one frozen
training run, no further experiments) no longer applies.

**Decision: drop `h3_cell`/`geohash` as model inputs, add neighbor-averaged
features.** Two changes, both required together:
1. `REDUCED_SPATIAL_CATEGORICAL_FEATURES` (already defined in ADR-019's
   experiment but never adopted into the actual training pipeline) is now
   the production categorical feature set — `train.py` trains on it instead
   of the full `CATEGORICAL_FEATURES`. `h3_cell` itself is kept as a
   dataframe column (serving lookups, spatial-holdout grouping) — it's
   removed only as a model *input*.
2. New neighbor-averaged features (`backend/app/features/spatial.py`'s
   `add_neighbor_averaged_features`, called once in `spatial.py` for
   density/junction-mix columns and once more in `rolling.py` for the
   real-time intensity columns): for each row, the average of
   `hotspot_frequency`/`violation_density`/`junction_density`/
   `police_station_density`/`rolling_hotspot_intensity`/
   `violations_last_15m` across the cell's H3 ring-1 neighbors, evaluated
   as-of that row's own timestamp via `merge_asof` (leakage-safe — see the
   function's docstring). This is the genuinely transferable spatial signal
   ADR-019 didn't have: a cell the model has never seen can still inherit
   "the neighborhood is hot" from cells it HAS seen, which raw cell-ID
   categorical encoding cannot provide.

**Result, measured via the same spatial holdout methodology as ADR-016:**
PR-AUC drop on unseen cells improves from **7.88% (ADR-016 baseline) /
7.09% (re-measured on this codebase before the fix) to 6.32%** — a real,
verified improvement (re-run via `backend/app/models/spatial_holdout.py`,
results written fresh on every retrain to `docs/spatial_holdout_result.json`
rather than hardcoded). **This does NOT cross the original 5% acceptance
bar — verdict stays FAIL, not PASS.**

**Things tried that did NOT help further (so the next person doesn't
re-try them):** widening the neighbor ring to k=2/k=3 (no measurable
change, ~6.0-6.9% across ring sizes); additionally dropping
`junction_name`/`police_station` as further location-correlated
categoricals (6.05% vs 6.07% — negligible). The remaining ~6% gap looks
like a genuine floor given what's derivable from this dataset alone (no
external geographic/road-network data permitted, per ADR-001), not a
tuning oversight.

**Honest framing for the pitch:** this is a measured ~20% relative
improvement in spatial generalization, not a fixed problem. Say "reduced
the spatial generalization gap from 7.9% to 6.3% by removing cell-identity
memorization and adding neighborhood-aggregated signal" — not "fixed
spatial generalization."

---

## ADR-023: Risk score weights and band cutoffs are fit, not hand-picked — and why naive fitting fails

**Context:** ADR-020's `risk_score` formula used hand-picked weights
(0.40/0.30/0.20/0.10) and band cutoffs, explicitly flagged elsewhere
(FINAL_SUMMARY.md) as "documented assumptions" rather than validated
values. There is still no ground-truth congestion/enforcement-outcome data
in the provided dataset (ADR-001 holds) — `target_count_60m` (actual
realized violation count in the next 60 minutes) is the best available
outcome proxy for "real-world impact."

**First attempt failed instructively:** plain non-negativity-constrained
regression (NNLS) of the 4 raw risk components against `target_count_60m`
on the train split collapsed to **100% weight on `normalized_predicted_count`,
0% on the other three.** This is not a bug, it's a near-tautology: the
regressor was LITERALLY trained to predict `target_count_60m`, so
regressing that same target against its own prediction trivially wins all
the weight, zeroing out `hotspot_probability`/`persistence`/
`recent_intensity` and reducing the "composite" score to "just use the
regressor's number" — which defeats the purpose of a multi-factor score
and makes "top contributing factors" meaningless (3 of 4 always read zero).

**Fix: ridge-regularized NNLS** (`backend/app/models/risk_score.py`,
`fit_risk_weights`/`_nnls_ridge`) — augments the NNLS system with an L2
penalty (standard trick: append `sqrt(alpha)*I` rows), which spreads weight
across the 4 components (pairwise correlation 0.48-0.63, confirmed via
`components.corr()`) instead of collapsing onto whichever one is closest to
the fitting target. The regularization strength isn't a fixed magic
number — `fit_risk_weights` searches a candidate list smallest-first and
keeps the first fit where no single component exceeds 75% of total weight,
so it applies the *minimum* regularization needed to avoid collapse rather
than an arbitrarily strong one. Result on the current train window:
`{hotspot_probability: 0.023, normalized_predicted_count: 0.701,
persistence: 0.145, recent_intensity: 0.131}` — predicted_count is still
(correctly) the most informative single signal, but the other three now
carry real, non-zero weight.

**Band cutoffs are fit the same way as ADR-020 originally did** (50th/85th/
97th percentile of train-period risk scores) but now computed fresh from
the fitted weights every retrain, rather than hardcoded module constants.
`WEIGHTS`/`RISK_BANDS` (old module-level constants) are replaced by one
`RiskParams` dataclass, persisted to `ml/models/risk_params.json` and
refit by `train.run()` on every retrain (see ADR-024) — so weights, bands,
and min-max scaling all stay consistent with whichever model version is
currently deployed, instead of three separately-maintained hardcoded values.

**Honest framing:** this is a data-driven *proxy* fit against the best
available outcome signal, not a measured causal weight — there is still no
ground-truth traffic-congestion data to fit against directly (ADR-001).

---

## ADR-024: Retraining pipeline + admin API — closes the "frozen model" gap

**Problem this closes:** prior to this ADR, incorporating new
police-uploaded violation data required manually rerunning
`build_features.py`/`train.py` and rebuilding+redeploying the Docker image
— there was no mechanism reachable from the running API (`backend/app/main.py`
only exposed `GET` routes; models/`docs/leaderboard.csv`/parquet were baked
into the image at build time, per `backend/Dockerfile`).

**Decision: a master, appendable raw CSV, separate from the frozen
hackathon-provided dataset.** `backend/app/ingestion/raw_store.py` maintains
`data/raw/violations_master.csv`, seeded once from `violations_raw.csv` (the
original file is never written to — only read, once, to seed the copy).
`append_new_violations` validates against the existing schema contract
(`schema.py`'s `validate_schema`/`REQUIRED_NON_NULL`), dedupes by `id`
against the master file, and reports added/duplicate/invalid counts rather
than a bare success/failure.

**Decision: one orchestrator function, not a new pipeline.**
`backend/app/models/retrain.py`'s `run_pipeline()` sequences the EXISTING
standalone scripts (`build_features.run()` → `train.run()` →
`generate_phase5_artifacts.run()`) rather than reimplementing them — each
already worked standalone (`python -m app.features.build_features`, etc.);
this only adds archive/rollback bookkeeping (`ml/models/archive/<timestamp>/`,
copied before any artifact is overwritten) on top. `train.run()` itself
now also refits risk params (ADR-023) and re-runs the spatial holdout check
(ADR-022) as part of every retrain — "retrain" means the whole stack
refreshes together, not just the classifier weights.

**Decision: FastAPI `BackgroundTasks` + in-memory job dict, not Celery/
APScheduler.** Neither is a project dependency, and a single in-process
background task is enough for one retrain at a time on a hackathon-scale
deployment. `POST /admin/retrain` returns a `job_id` immediately;
`GET /admin/retrain/{job_id}` polls status (PENDING/RUNNING/SUCCESS/FAILED).
On success, the background task calls new `reload_state()` functions on
`forecast_service`/`risk_snapshot`/`metrics_service` (each just clears
cached module globals) so the running process picks up the retrained model
**without a restart**.

**Decision: minimal shared-secret guard, not a full auth system.** All
`/admin/*` routes require an `X-Admin-Token` header matching
`settings.admin_api_token` (env var; empty/unset disables the routes
entirely with a 503, not a silent no-op). These routes can overwrite
production models, so "unauthenticated by default" was not acceptable —
but building real user auth was out of scope for what this gap needed.

**Disclosed limitation, not hidden:** on ephemeral-filesystem hosts
(Render/HF Space free tier), `data/raw/violations_master.csv` and retrained
artifacts won't survive a redeploy unless a persistent volume is attached.
The retrain mechanism works correctly within a running process's lifetime;
surviving redeploys is a deployment-infrastructure decision (attach a
volume), not a code gap.
