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
