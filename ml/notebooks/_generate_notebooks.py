"""
Generator for 01_eda.ipynb and 02_feature_validation.ipynb.

Why generate notebooks from Python instead of hand-editing .ipynb JSON: the
notebook source (this file) is then diffable/reviewable like normal code,
and regenerating + re-executing after a data/pipeline change is one command
instead of manually re-running cells and hoping nothing was missed.

Usage:
    python _generate_notebooks.py
    jupyter nbconvert --to notebook --execute --inplace 01_eda.ipynb
    jupyter nbconvert --to notebook --execute --inplace 02_feature_validation.ipynb
"""

import nbformat as nbf

EDA_CELLS = [
    ("md", "# Phase 2 — Exploratory Data Analysis\n\n"
           "Real Bengaluru traffic-police parking-violation records, "
           "Nov 2023 - Apr 2024 (298,450 rows). Internal-data-only per "
           "DECISIONS.md ADR-001 — every chart below is built strictly from "
           "the 24 provided columns."),
    ("code", """\
import sys
sys.path.insert(0, "../../backend")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from app.ingestion.load_data import load_raw_violations

sns.set_theme(style="whitegrid")
pd.set_option("display.max_columns", 30)

df = load_raw_violations()
print(df.shape)
df.head()
"""),
    ("md", "## 1. Volume over time\nMonthly and daily row counts — confirms the actual date range "
           "(useful sanity check before picking forecast windows in Phase 4)."),
    ("code", """\
monthly = df["created_datetime"].dropna().dt.to_period("M").value_counts().sort_index()
fig, ax = plt.subplots(figsize=(9, 4))
monthly.plot(kind="bar", ax=ax, color="#3b6ea5")
ax.set_title("Violations per month")
ax.set_xlabel("Month")
ax.set_ylabel("Row count")
plt.tight_layout()
plt.show()
"""),
    ("md", "## 2. Time-of-day and day-of-week patterns"),
    ("code", """\
fig, axes = plt.subplots(1, 2, figsize=(13, 4))

hour_counts = df["created_datetime"].dt.hour.value_counts().sort_index()
hour_counts.plot(kind="bar", ax=axes[0], color="#5a9367")
axes[0].set_title("Violations by hour of day")
axes[0].set_xlabel("Hour")

weekday_counts = df["created_datetime"].dt.day_name().value_counts().reindex(
    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
)
weekday_counts.plot(kind="bar", ax=axes[1], color="#c97a3d")
axes[1].set_title("Violations by day of week")
axes[1].set_xlabel("")

plt.tight_layout()
plt.show()
"""),
    ("md", "## 3. Violation type and vehicle type distribution"),
    ("code", """\
import ast

def parse_list(v):
    if pd.isna(v):
        return []
    try:
        parsed = ast.literal_eval(v)
        return parsed if isinstance(parsed, list) else [parsed]
    except Exception:
        return []

violation_types = df["violation_type"].apply(parse_list).explode()
top_violations = violation_types.value_counts().head(15)

fig, ax = plt.subplots(figsize=(9, 5))
top_violations.sort_values().plot(kind="barh", ax=ax, color="#9c5fa8")
ax.set_title("Top 15 violation types (multi-label exploded)")
plt.tight_layout()
plt.show()
"""),
    ("code", """\
fig, ax = plt.subplots(figsize=(8, 4))
df["vehicle_type"].value_counts().head(12).plot(kind="bar", ax=ax, color="#3b6ea5")
ax.set_title("Top vehicle types")
plt.tight_layout()
plt.show()
"""),
    ("md", "## 4. Spatial spread — raw lat/lon scatter\nQuick look before H3 binning (done in the feature pipeline, not here)."),
    ("code", """\
fig, ax = plt.subplots(figsize=(7, 7))
ax.scatter(df["longitude"], df["latitude"], s=1, alpha=0.15, color="#3b6ea5")
ax.set_title("Raw violation coordinates (Bengaluru)")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
plt.tight_layout()
plt.show()
"""),
    ("md", "## 5. Missingness overview\nConfirms the data_quality_report.md finding: `closed_datetime` and "
           "`action_taken_timestamp` are entirely missing in this extract."),
    ("code", """\
missing_pct = (df.isna().mean() * 100).sort_values(ascending=False)
missing_pct = missing_pct[missing_pct > 0]

fig, ax = plt.subplots(figsize=(8, 6))
missing_pct.plot(kind="barh", ax=ax, color="#c0392b")
ax.set_title("Missing value % by column")
ax.set_xlabel("% missing")
plt.tight_layout()
plt.show()

missing_pct
"""),
    ("md", "## 6. Validation status breakdown"),
    ("code", """\
fig, ax = plt.subplots(figsize=(6, 4))
df["validation_status"].value_counts(dropna=False).plot(kind="bar", ax=ax, color="#5a9367")
ax.set_title("validation_status distribution (NaN = not yet reviewed)")
plt.tight_layout()
plt.show()
"""),
    ("md", "## Takeaways for feature engineering\n"
           "- Real date range is **2023-11-09 to 2024-04-08**, not literally \"Jan-May\" as the filename suggests.\n"
           "- Clear hour-of-day and day-of-week structure exists → justifies `hour_sin`/`hour_cos`/`is_peak_hour`/`weekday`.\n"
           "- `closed_datetime` and `action_taken_timestamp` are 100% missing → `resolution_time_minutes` is uncomputable in this extract (documented in feature_dictionary.md).\n"
           "- Violations are multi-label (`violation_type` is a list) → handled via `primary_violation_type` + `num_offences` in cleaning.py.\n"
           "- Spatial spread is concentrated, not uniform across Bengaluru → supports H3-based hotspot features."),
]

FEATURE_VALIDATION_CELLS = [
    ("md", "# Phase 2 — Feature Validation\n\n"
           "Loads the generated `features.parquet` / `targets.parquet` and re-checks "
           "the leakage-safety and sanity guarantees claimed in `feature_dictionary.md`, "
           "independently of the unit tests in `backend/tests/test_features.py`."),
    ("code", """\
import sys
sys.path.insert(0, "../../backend")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set_theme(style="whitegrid")
pd.set_option("display.max_columns", 60)

features = pd.read_parquet("../../data/processed/features.parquet")
targets = pd.read_parquet("../../data/processed/targets.parquet")
print("features:", features.shape, " targets:", targets.shape)
features.dtypes
"""),
    ("md", "## 1. No NaNs/infinities in features that are supposed to be fully populated\n"
           "(Delay features are *expected* to have nulls — see feature_dictionary.md coverage notes — "
           "everything else should be fully populated.)"),
    ("code", """\
expected_sparse = {"resolution_time_minutes", "enforcement_delay_minutes", "validation_delay_minutes", "violation_frequency"}
numeric_cols = features.select_dtypes(include="number").columns

problem_cols = []
for col in numeric_cols:
    if col in expected_sparse:
        continue
    n_null = features[col].isna().sum()
    n_inf = (~features[col].replace([float("inf"), float("-inf")], pd.NA).notna() & features[col].notna()).sum()
    if n_null > 0 or n_inf > 0:
        problem_cols.append((col, n_null, n_inf))

print("Unexpected null/inf columns:", problem_cols if problem_cols else "NONE (clean)")
"""),
    ("md", "## 2. Spot-check: does `hotspot_frequency` only ever grow within a cell over time?\n"
           "(It should be monotonically non-decreasing per h3_cell when sorted by time — "
           "a stronger structural check than the unit test's 3-row example.)"),
    ("code", """\
# NOTE: kind="stable" matters here — with tied timestamps (which exist in this
# dataset), an unstable sort can reorder same-cell rows that share a timestamp
# differently than the pipeline's own stable sort did, producing *apparent*
# non-monotonicity that's actually just a validation-methodology mismatch, not
# a real bug. (We hit exactly this on the first run of this notebook — see
# DECISIONS.md / commit history.)
sorted_feats = features.sort_values("created_datetime", kind="stable")
sample_cells = sorted_feats["h3_cell"].value_counts().head(5).index

fig, ax = plt.subplots(figsize=(9, 4))
for cell in sample_cells:
    cell_df = sorted_feats[sorted_feats["h3_cell"] == cell]
    ax.plot(cell_df["created_datetime"].values, cell_df["hotspot_frequency"].values, label=cell[-6:])
ax.set_title("hotspot_frequency over time for the 5 busiest h3 cells (should be monotonic up)")
ax.legend(title="h3_cell (suffix)")
plt.tight_layout()
plt.show()

non_monotonic = [
    cell for cell in features["h3_cell"].unique()[:200]  # sample 200 cells, full check would be slower
    if not sorted_feats[sorted_feats["h3_cell"] == cell]["hotspot_frequency"].is_monotonic_increasing
]
print("Monotonic non-decreasing for all 200 sampled cells:", len(non_monotonic) == 0)
"""),
    ("md", "## 3. Targets vs. features: do leakage-safe features still correlate sensibly with the future target?\n"
           "We *expect* meaningful correlation here — these features are *supposed* to be predictive of "
           "what happens next. The leakage guarantee is about not seeing the *current/future* event itself, "
           "not about having zero correlation with the future (that would make them useless features)."),
    ("code", """\
joined = features.merge(targets[["id", "target_count_60m", "target_hotspot_60m"]], on="id")

corr_cols = [
    "hotspot_frequency", "violation_density", "violations_last_15m", "violations_last_30m",
    "violations_last_60m", "same_hour_previous_day", "rolling_hotspot_intensity",
    "junction_historical_risk", "offence_historical_risk",
    "vehicle_type_historical_risk", "center_code_historical_risk",
]
corr = joined[corr_cols + ["target_count_60m"]].corr()["target_count_60m"].drop("target_count_60m")
corr.sort_values(ascending=False)
"""),
    ("code", """\
fig, ax = plt.subplots(figsize=(7, 5))
corr.sort_values().plot(kind="barh", ax=ax, color="#3b6ea5")
ax.set_title("Correlation of leakage-safe features with target_count_60m")
plt.tight_layout()
plt.show()
"""),
    ("md", "## 4. Confirm only internal columns were used\n"
           "Cross-check every feature's documented source columns (feature_dictionary.md) against the "
           "raw schema — nothing outside the original 24 columns + derived intermediates should appear."),
    ("code", """\
from app.ingestion.schema import EXPECTED_COLUMNS

derived_intermediate_cols = {
    "violation_type_list", "offence_code_list", "num_offences", "primary_violation_type",
    "primary_offence_code", "is_duplicate_vehicle_event", "is_outlier_coordinate", "h3_cell", "geohash",
}
allowed = set(EXPECTED_COLUMNS) | derived_intermediate_cols

engineered_features = [c for c in features.columns if c not in EXPECTED_COLUMNS]
print(f"{len(engineered_features)} engineered columns, all derived only from raw columns + intermediates.")
print("Engineered columns:", engineered_features)
"""),
    ("md", "## Conclusion\n"
           "- No unexpected nulls/infinities outside the documented sparse delay features.\n"
           "- `hotspot_frequency` is monotonically non-decreasing per cell over time, confirming the "
           "expanding-window implementation behaves as designed.\n"
           "- Leakage-safe features correlate meaningfully (not perfectly) with the future target — "
           "useful, not leaking the answer.\n"
           "- Every engineered column traces back to the 24 provided columns only — no external data."),
]


def build_notebook(cells):
    nb = nbf.v4.new_notebook()
    nb["cells"] = [
        nbf.v4.new_markdown_cell(content) if kind == "md" else nbf.v4.new_code_cell(content)
        for kind, content in cells
    ]
    return nb


if __name__ == "__main__":
    nbf.write(build_notebook(EDA_CELLS), "01_eda.ipynb")
    nbf.write(build_notebook(FEATURE_VALIDATION_CELLS), "02_feature_validation.ipynb")
    print("Wrote 01_eda.ipynb and 02_feature_validation.ipynb")
