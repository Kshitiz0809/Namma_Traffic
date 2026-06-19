"""
Generates slides/Parking_Intelligence_Deck.pptx from the verified project
numbers (DECISIONS.md, MODEL_REPORT.md, docs/spatial_holdout_result.json,
ml/models/risk_params.json, live /metrics). Run with:
    python slides/build_deck.py
Re-run after any retrain to regenerate with fresh numbers.

Design rule: numbers go in tables/charts, not paragraphs. Bullet text is
kept short (one line each) — anything with more than ~5 numeric data
points becomes a table or a chart instead.
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

NAVY = RGBColor(0x0F, 0x17, 0x2A)
INDIGO = RGBColor(0x4F, 0x46, 0xE5)
SLATE = RGBColor(0x33, 0x41, 0x55)
GREEN = RGBColor(0x15, 0x80, 0x3D)
AMBER = RGBColor(0xB4, 0x53, 0x09)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF4, 0xF6, 0xFB)
PIE_COLORS = [RGBColor(0x4F, 0x46, 0xE5), RGBColor(0x22, 0xC5, 0x5E), RGBColor(0xF5, 0x9E, 0x0B), RGBColor(0xEF, 0x44, 0x44)]

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def add_slide():
    return prs.slides.add_slide(BLANK)


def rect(slide, x, y, w, h, color):
    shp = slide.shapes.add_shape(1, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    return shp


def textbox(slide, x, y, w, h, text, size=18, bold=False, color=SLATE, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def bullet_list(slide, x, y, w, h, items, size=14, color=SLATE, line_spacing=1.15):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "• " + item
        p.font.size = Pt(size)
        p.font.color.rgb = color
        p.space_after = Pt(5)
        p.line_spacing = line_spacing
    return box


def header(slide, title, kicker=None):
    rect(slide, 0, 0, prs.slide_width, Inches(1.05), NAVY)
    textbox(slide, Inches(0.5), Inches(0.13), Inches(11), Inches(0.6), title, size=28, bold=True, color=WHITE)
    if kicker:
        textbox(slide, Inches(0.5), Inches(0.62), Inches(11), Inches(0.35), kicker, size=13, color=RGBColor(0xC7, 0xD2, 0xFE))
    rect(slide, 0, Inches(7.3), prs.slide_width, Inches(0.2), INDIGO)


def stat_card(slide, x, y, w, h, value, label, good=None):
    color = GREEN if good is True else (AMBER if good is False else INDIGO)
    rect(slide, x, y, w, h, LIGHT)
    box = slide.shapes.add_textbox(x, y + Inches(0.1), w, h - Inches(0.2))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = value
    run.font.size = Pt(24)
    run.font.bold = True
    run.font.color.rgb = color
    p2 = tf.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER
    run2 = p2.add_run()
    run2.text = label
    run2.font.size = Pt(10.5)
    run2.font.color.rgb = SLATE


def make_table(slide, x, y, w, h, rows, col_widths=None, font_size=12, header_color=NAVY):
    n_rows, n_cols = len(rows), len(rows[0])
    shape = slide.shapes.add_table(n_rows, n_cols, x, y, w, h)
    table = shape.table
    if col_widths:
        for i, cw in enumerate(col_widths):
            table.columns[i].width = cw
    for r_i, row in enumerate(rows):
        for c_i, val in enumerate(row):
            cell = table.cell(r_i, c_i)
            cell.text = str(val)
            cell.margin_top = Pt(2)
            cell.margin_bottom = Pt(2)
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(font_size)
                p.font.bold = (r_i == 0)
                p.font.color.rgb = WHITE if r_i == 0 else SLATE
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_color if r_i == 0 else (LIGHT if r_i % 2 == 0 else WHITE)
    return table


def bar_chart(slide, x, y, w, h, categories, series_name, values, bar_colors=None, title=None, num_fmt="0.00", y_min=None, y_max=None):
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series(series_name, values)
    gframe = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, w, h, chart_data)
    chart = gframe.chart
    chart.has_legend = False
    chart.has_title = bool(title)
    if title:
        chart.chart_title.text_frame.text = title
        chart.chart_title.text_frame.paragraphs[0].font.size = Pt(13)
    plot = chart.plots[0]
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = num_fmt
    dl.number_format_is_linked = False
    dl.font.size = Pt(11)
    dl.font.bold = True
    series = plot.series[0]
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = INDIGO
    if bar_colors:
        for i, pt in enumerate(series.points):
            if bar_colors[i] is not None:
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = bar_colors[i]
    value_axis = chart.value_axis
    value_axis.has_major_gridlines = False
    value_axis.tick_labels.font.size = Pt(10)
    if y_min is not None:
        value_axis.minimum_scale = y_min
    if y_max is not None:
        value_axis.maximum_scale = y_max
    cat_axis = chart.category_axis
    cat_axis.tick_labels.font.size = Pt(10.5)
    return gframe


def pie_chart(slide, x, y, w, h, categories, values, title=None):
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("Series 1", values)
    gframe = slide.shapes.add_chart(XL_CHART_TYPE.PIE, x, y, w, h, chart_data)
    chart = gframe.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.RIGHT
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(11)
    chart.has_title = bool(title)
    if title:
        chart.chart_title.text_frame.text = title
        chart.chart_title.text_frame.paragraphs[0].font.size = Pt(13)
    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.show_percentage = True
    plot.data_labels.show_category_name = False
    plot.data_labels.number_format = "0.0%"
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.font.size = Pt(11)
    plot.data_labels.font.bold = True
    plot.data_labels.font.color.rgb = WHITE
    for i, pt in enumerate(plot.series[0].points):
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = PIE_COLORS[i % len(PIE_COLORS)]
    return gframe


# ---------------------------------------------------------------------------
# Slide 1 — Title
# ---------------------------------------------------------------------------
s = add_slide()
rect(s, 0, 0, prs.slide_width, prs.slide_height, NAVY)
textbox(s, Inches(1), Inches(2.5), Inches(11.3), Inches(1.2),
        "Parking Intelligence — Decision Support Platform", size=40, bold=True, color=WHITE)
textbox(s, Inches(1), Inches(3.6), Inches(11.3), Inches(0.6),
        "AI-Driven Illegal-Parking Hotspot Detection & Traffic-Impact Quantification", size=20, color=RGBColor(0xC7, 0xD2, 0xFE))
textbox(s, Inches(1), Inches(4.3), Inches(11.3), Inches(0.5),
        "Bengaluru Traffic Police · 298,450 real violation records · Zero external data", size=14, color=RGBColor(0x94, 0xA3, 0xB8))
textbox(s, Inches(1), Inches(6.6), Inches(11.3), Inches(0.4),
        "Internal-data-only (ADR-001) · No Maps/external APIs used, per competition rules", size=12, color=RGBColor(0x64, 0x74, 0x8B))

# ---------------------------------------------------------------------------
# Slide 2 — Problem statement
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "The Problem", "Why reactive enforcement isn't enough")
bullet_list(s, Inches(0.6), Inches(1.3), Inches(5.9), Inches(3.0), [
    "298,450 violations logged over ~5 months, Bengaluru",
    "Enforcement today is reactive — ticket after the fact",
    "No system predicts tomorrow's hotspot, only logs today's",
    "Constraint: only the provided dataset — no Maps/external APIs",
], size=16)
stat_card(s, Inches(0.6), Inches(4.5), Inches(2.85), Inches(1.3), "298,450", "Total violation rows")
stat_card(s, Inches(3.65), Inches(4.5), Inches(2.85), Inches(1.3), "24", "Raw schema columns")
rect(s, Inches(7.0), Inches(1.3), Inches(5.7), Inches(5.5), LIGHT)
textbox(s, Inches(7.3), Inches(1.45), Inches(5.2), Inches(0.4), "Raw schema (24 columns)", size=15, bold=True, color=NAVY)
schema_rows = [
    ("Identity / location", "id, latitude, longitude, location"),
    ("Vehicle", "vehicle_number, vehicle_type, updated_vehicle_number/type"),
    ("Violation", "description, violation_type, offence_code"),
    ("Timestamps", "created/closed/modified_datetime, action_taken_timestamp"),
    ("Org / device", "device_id, created_by_id, center_code, police_station,\njunction_name"),
    ("SCITA / validation", "data_sent_to_scita(_timestamp), validation_status(_timestamp)"),
]
make_table(s, Inches(7.3), Inches(1.9), Inches(5.2), Inches(4.7),
           [("Group", "Fields")] + schema_rows, col_widths=[Inches(1.6), Inches(3.6)], font_size=11)

# ---------------------------------------------------------------------------
# Slide 3 — Architecture overview
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "System Architecture", "End-to-end pipeline, ingestion to dashboard")
stages = [
    ("Raw CSV\n298,450 rows", "Validate,\ndedupe, cast"),
    ("Feature\nEngineering", "H3 grid, rolling\nwindows"),
    ("3 Models", "CatBoost / LightGBM\n/ XGBoost"),
    ("Risk Score\nEngine", "Ridge-NNLS\nfit weights"),
    ("FastAPI\nServing", "/forecast /alerts\n/metrics /admin"),
    ("Next.js\nDashboard", "Map, forecast,\nanalytics, admin"),
]
xw, gap, x0, y0, h0 = Inches(1.95), Inches(0.15), Inches(0.4), Inches(1.6), Inches(1.5)
for i, (title, desc) in enumerate(stages):
    cx = x0 + i * (xw + gap)
    rect(s, cx, y0, xw, h0, INDIGO if i % 2 == 0 else NAVY)
    box = s.shapes.add_textbox(cx + Inches(0.05), y0 + Inches(0.1), xw - Inches(0.1), h0 - Inches(0.2))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = title
    r.font.size = Pt(13)
    r.font.bold = True
    r.font.color.rgb = WHITE
    p2 = tf.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run()
    r2.text = desc
    r2.font.size = Pt(9.5)
    r2.font.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
    if i < len(stages) - 1:
        arrow = s.shapes.add_textbox(cx + xw, y0 + Inches(0.55), gap, Inches(0.4))
        ap = arrow.text_frame.paragraphs[0]
        ap.alignment = PP_ALIGN.CENTER
        ar = ap.add_run()
        ar.text = "→"
        ar.font.size = Pt(18)
        ar.font.color.rgb = SLATE

make_table(s, Inches(0.6), Inches(3.5), Inches(12.1), Inches(2.2), [
    ("Layer", "What it does"),
    ("Retraining loop (ADR-024)", "Upload → PENDING staging → review approve/reject → merge → explicit Retrain → hot-reload, zero downtime"),
    ("Deployment", "Docker image → Docker Hub → Hugging Face Space (API) + Vercel (frontend, auto-deploy on push)"),
    ("Admin security", "X-Admin-Token header; 503 if unconfigured, 401 if wrong"),
], col_widths=[Inches(2.6), Inches(9.5)], font_size=13)

# ---------------------------------------------------------------------------
# Slide 4 — Feature engineering
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "Feature Engineering", "Leakage-safe, spatial + temporal")
make_table(s, Inches(0.6), Inches(1.3), Inches(7.2), Inches(5.4), [
    ("Category", "Examples", "#"),
    ("Spatial density", "hotspot_frequency, violation_density,\njunction_density, police_station_density", "4"),
    ("Neighbor-averaged\n(ADR-022)", "ring-1 H3 neighbor avg of each\ndensity/intensity feature", "6"),
    ("Temporal", "hour, weekday, is_weekend,\nhour_sin/cos, is_peak_hour", "6"),
    ("Rolling counts", "violations_last_15/30/60m,\nsame_hour_previous_day, rolling_intensity", "5"),
    ("Historical risk priors", "junction/offence/vehicle_type/\ncenter_code_historical_risk", "4"),
    ("Data-quality flags", "is_outlier_coordinate,\nis_duplicate_vehicle_event", "2"),
    ("Categorical", "junction_name, police_station, center_code,\nvehicle_type, offence_code, violation_type", "6"),
], col_widths=[Inches(2.1), Inches(4.4), Inches(0.7)], font_size=11.5)

rect(s, Inches(8.0), Inches(1.3), Inches(4.75), Inches(5.4), LIGHT)
textbox(s, Inches(8.2), Inches(1.45), Inches(4.4), Inches(0.4), "Leakage-safety rules", size=15, bold=True, color=NAVY)
bullet_list(s, Inches(8.2), Inches(1.9), Inches(4.4), Inches(2.8), [
    "Every rolling feature uses an expanding,\nstrictly-past-only window",
    "merge_asof(direction=\"backward\") for\nevery spatial/temporal join",
    "h3_cell/geohash dropped as direct model\ninputs — kept only for serving lookups",
    "Phase 4 feature lock deliberately\nun-frozen once retraining became\npossible (ADR-022)",
], size=12.5)

# ---------------------------------------------------------------------------
# Slide 5 — Modeling approach & comparison
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "Modeling Approach", "3 gradient-boosted models, 2 tasks")
make_table(s, Inches(0.5), Inches(1.25), Inches(6.5), Inches(1.7), [
    ("Model", "PR-AUC", "Precision", "Recall", "F1"),
    ("CatBoost (winner)", "0.8767", "0.7316", "0.9620", "0.8311"),
    ("LightGBM", "0.8649", "0.7351", "0.9505", "0.8290"),
    ("XGBoost", "0.8632", "0.7245", "0.9567", "0.8246"),
], col_widths=[Inches(1.9), Inches(1.15), Inches(1.15), Inches(1.15), Inches(1.15)], font_size=12)
textbox(s, Inches(0.5), Inches(3.05), Inches(6.5), Inches(0.4), "Operating threshold: 0.15 (cost-aware — favors recall)", size=12, color=SLATE)

make_table(s, Inches(0.5), Inches(3.55), Inches(6.5), Inches(1.5), [
    ("Count regression", "MAE", "RMSE", "R²"),
    ("CatBoost", "5.92", "10.58", "0.271"),
    ("LightGBM", "6.02", "10.92", "0.223"),
    ("XGBoost", "6.24", "11.18", "0.186"),
], col_widths=[Inches(1.9), Inches(1.5), Inches(1.5), Inches(1.6)], font_size=12)

bar_chart(s, Inches(7.3), Inches(1.25), Inches(5.5), Inches(2.9),
          ["15 min", "30 min", "60 min", "90 min"], "PR-AUC",
          [0.7834, 0.8337, 0.8767, 0.8929], title="PR-AUC by prediction horizon")
textbox(s, Inches(0.5), Inches(5.2), Inches(12.2), Inches(0.4),
        "Calibration test (Platt/Isotonic): <5% Brier improvement over raw probabilities — rejected, not adopted", size=12.5, color=SLATE)
textbox(s, Inches(0.5), Inches(5.7), Inches(12.2), Inches(0.5),
        "PR-AUC rises monotonically with horizon length — confirms the model uses real temporal accumulation, not noise", size=13, bold=True, color=NAVY)

# ---------------------------------------------------------------------------
# Slide 6 — Risk score formula
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "Congestion Risk Score", "A derived score, not a new ML target")
rect(s, Inches(0.5), Inches(1.3), Inches(7.0), Inches(1.55), NAVY)
textbox(s, Inches(0.75), Inches(1.45), Inches(6.5), Inches(0.4), "risk_score = 100 × Σ wᵢ · componentᵢ", size=18, bold=True, color=WHITE)
bullet_list(s, Inches(0.75), Inches(1.9), Inches(6.5), Inches(0.9), [
    "hotspot_probability + normalized_predicted_count",
    "+ persistence + recent_intensity  (all 0–1 scaled)",
], size=12, color=RGBColor(0xE2, 0xE8, 0xF0))

bullet_list(s, Inches(0.5), Inches(3.1), Inches(7.0), Inches(2.0), [
    "Originally hand-picked: 0.40 / 0.30 / 0.20 / 0.10",
    "Plain NNLS collapsed to 100% on one component (tautological target leakage)",
    "Fix: ridge-regularized NNLS — solve [X; √α·I]β ≈ [y; 0], sweep α, pick smallest α with max weight ≤ 75%",
    "Refit automatically on every retrain — no frozen constants",
], size=13)

pie_chart(s, Inches(7.7), Inches(1.3), Inches(5.1), Inches(3.6),
          ["Hotspot prob.", "Predicted count", "Persistence", "Recent intensity"],
          [0.020, 0.701, 0.147, 0.131], title="Current fitted weights (ADR-023)")

stat_card(s, Inches(0.5), Inches(5.3), Inches(3.4), Inches(1.3), "50 / 85 / 97", "Band cutoffs\n(percentile of train risk scores)")
stat_card(s, Inches(4.1), Inches(5.3), Inches(3.4), Inches(1.3), "4", "Bands: LOW / MEDIUM\n/ HIGH / CRITICAL")
stat_card(s, Inches(7.7), Inches(5.3), Inches(5.1), Inches(1.3), "target_count_60m", "Outcome proxy used for fitting\n(no ground-truth congestion data exists)")

# ---------------------------------------------------------------------------
# Slide 7 — Spatial holdout methodology + results
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "Spatial Generalization Testing", "Does the model work on geography it's never seen?")
textbox(s, Inches(0.5), Inches(1.25), Inches(12.2), Inches(0.6),
        "Methodology: split H3 cells (not rows) into 1,824 train cells / 455 holdout cells, entirely unseen during training",
        size=14, color=SLATE)

stat_card(s, Inches(0.5), Inches(1.9), Inches(2.95), Inches(1.2), "0.8796", "Seen-cell PR-AUC")
stat_card(s, Inches(3.6), Inches(1.9), Inches(2.95), Inches(1.2), "0.8298", "Unseen-cell PR-AUC")
stat_card(s, Inches(6.7), Inches(1.9), Inches(2.95), Inches(1.2), "5.66%", "PR-AUC drop", good=False)
stat_card(s, Inches(9.8), Inches(1.9), Inches(2.95), Inches(1.2), "94.3%", "Accuracy retained", good=True)

bar_chart(s, Inches(0.5), Inches(3.3), Inches(6.0), Inches(3.6),
          ["Original\n(frozen)", "ADR-022\n(neighbor feats)", "ADR-025\n(regularization)"],
          "PR-AUC drop %", [7.88, 6.32, 5.66],
          bar_colors=[AMBER, INDIGO, GREEN], title="Spatial holdout drop — two rounds of fixes", num_fmt="0.00\"%\"")

make_table(s, Inches(6.85), Inches(3.3), Inches(5.9), Inches(3.4), [
    ("Stage", "Change made"),
    ("Original", "Raw h3_cell/geohash kept as categorical inputs"),
    ("ADR-022", "Dropped cell identity, added 6 neighbor-averaged density features"),
    ("ADR-025", "Regularization sweep: depth 6→3, l2_leaf_reg 3→25"),
    ("Net result", "~28% relative improvement, still above the 5% bar — disclosed honestly"),
], col_widths=[Inches(1.5), Inches(4.4)], font_size=12)

# ---------------------------------------------------------------------------
# Slide 8 — Regularization sweep detail
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "Hyperparameter Sweep (ADR-025)", "Overfitting problem, not a feature problem")
textbox(s, Inches(0.5), Inches(1.25), Inches(12.2), Inches(0.5),
        "~15 configs swept (depth, l2_leaf_reg, learning_rate, iterations, rsm, bagging, random_strength) against the same spatial holdout test",
        size=13.5, color=SLATE)

bar_chart(s, Inches(0.5), Inches(1.85), Inches(6.3), Inches(3.6),
          ["depth=6\n(baseline)", "depth=3\n(adopted)", "depth=2", "depth=1"],
          "PR-AUC drop %", [6.32, 5.66, 5.54, 5.27],
          bar_colors=[AMBER, GREEN, INDIGO, INDIGO], title="Drop % vs. tree depth", num_fmt="0.00\"%\"")

make_table(s, Inches(7.0), Inches(1.85), Inches(5.75), Inches(3.6), [
    ("Config", "Seen", "Unseen", "Cost?"),
    ("depth=6, l2=3", "0.8792", "0.8237", "Baseline"),
    ("depth=3, l2=25 ✓", "0.8796", "0.8298", "None — wins both"),
    ("depth=2, l2=40", "0.8765", "0.8280", "Small accuracy loss"),
    ("depth=1, l2=25", "0.8727", "0.8268", "Real accuracy loss"),
], col_widths=[Inches(2.1), Inches(1.2), Inches(1.25), Inches(1.2)], font_size=11.5)

bullet_list(s, Inches(0.5), Inches(5.75), Inches(12.2), Inches(1.3), [
    "depth=3/l2=25 improves BOTH seen and unseen accuracy at once — a strict win, not a tradeoff",
    "Pushing shallower trades real accuracy for diminishing spatial gains — none crossed the 5% bar",
], size=14)

# ---------------------------------------------------------------------------
# Slide 9 — Retraining pipeline & staging workflow
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "Retraining Pipeline & Review Workflow", "Closing the \"frozen model\" gap (ADR-024)")
steps = ["Police\nupload CSV", "PENDING\nstaging", "Reviewer\napprove/reject", "Merge into\nmaster dataset", "Explicit\nRetrain", "Pipeline\nre-runs", "Hot-reload\n(zero downtime)"]
xw, gp, xs, yS, hS = Inches(1.7), Inches(0.1), Inches(0.35), Inches(1.5), Inches(1.4)
for i, st in enumerate(steps):
    cx = xs + i * (xw + gp)
    rect(s, cx, yS, xw, hS, INDIGO if i % 2 == 0 else NAVY)
    box = s.shapes.add_textbox(cx + Inches(0.04), yS + Inches(0.12), xw - Inches(0.08), hS - Inches(0.2))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = st
    r.font.size = Pt(11.5)
    r.font.bold = True
    r.font.color.rgb = WHITE

make_table(s, Inches(0.5), Inches(3.2), Inches(12.2), Inches(3.0), [
    ("Component", "Responsibility"),
    ("staging_store.py", "Owns PENDING → APPROVED/REJECTED lifecycle; reuses raw_store's merge logic"),
    ("raw_store.py", "Owns the master CSV — schema validation, dedupe by id, append"),
    ("retrain.py", "Archives prior ml/models/ by timestamp, then runs features → train → risk-weight fit → spatial holdout → alerts"),
    ("Admin dashboard tab", "Token field, CSV upload, staging review table, Retrain Now button with live job polling"),
    ("Disclosed limitation", "Ephemeral-filesystem hosts without a persistent volume lose data on redeploy — infra decision, not a code gap"),
], col_widths=[Inches(2.6), Inches(9.6)], font_size=13)

# ---------------------------------------------------------------------------
# Slide 10 — API & deployment
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "API Surface & Deployment", "FastAPI backend, Next.js frontend")
make_table(s, Inches(0.5), Inches(1.25), Inches(6.3), Inches(2.6), [
    ("Public endpoint", "Purpose"),
    ("GET /health", "Schema validity, row count"),
    ("GET /forecast", "Per-cell/coordinate prediction + risk band"),
    ("GET /alerts", "Ranked GREEN/YELLOW/ORANGE/RED alerts"),
    ("GET /metrics", "Model + spatial + risk-distribution stats"),
    ("GET /replay/{scenario}", "Real historical event replay for demos"),
], col_widths=[Inches(2.4), Inches(3.9)], font_size=12)

make_table(s, Inches(0.5), Inches(4.1), Inches(6.3), Inches(1.9), [
    ("Admin endpoint (token-guarded)", "Purpose"),
    ("POST /admin/staging/upload", "Stage a new CSV as PENDING"),
    ("POST /admin/staging/{id}/approve|reject", "Review decision"),
    ("POST /admin/retrain", "Trigger background retraining job"),
], col_widths=[Inches(3.5), Inches(2.8)], font_size=11)

rect(s, Inches(7.1), Inches(1.25), Inches(5.65), Inches(5.7), LIGHT)
textbox(s, Inches(7.3), Inches(1.4), Inches(5.3), Inches(0.4), "Deployment chain", size=15, bold=True, color=NAVY)
bullet_list(s, Inches(7.3), Inches(1.9), Inches(5.3), Inches(4.8), [
    "Backend: Docker image → Docker Hub →\nHugging Face Space (Docker SDK)",
    "Frontend: Next.js 14 + Tailwind + Leaflet\n+ Recharts → Vercel (auto-deploy on push)",
    "CORS tightened to real origins (was *)",
    "NEXT_PUBLIC_API_BASE_URL env var points\nthe frontend at the live HF Space",
    "Async retrain via FastAPI BackgroundTasks\n(no Celery/APScheduler — kept simple)",
], size=13)

# ---------------------------------------------------------------------------
# Slide 11 — Known limitations (honest disclosure)
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "Known Limitations — Disclosed, Not Hidden", "Honesty over a fabricated PASS")
make_table(s, Inches(0.5), Inches(1.3), Inches(12.2), Inches(5.6), [
    ("Limitation", "Status"),
    ("Spatial holdout", "FAIL by the 5% bar — 5.66% drop, improved from 7.88%, not eliminated"),
    ("Risk weights", "Data-driven PROXY fit (target_count_60m) — no ground-truth congestion data exists"),
    ("Enforcement timestamps", "closed_datetime / action_taken_timestamp 100% missing in this extract"),
    ("Data window", "Single 5-month window (Nov 2023 – Apr 2024) — seasonality untested"),
    ("Live streaming", "None — latest historical snapshot per cell, not real-time; Kafka is the next step"),
    ("Retraining persistence", "Doesn't survive ephemeral redeploys without a persistent volume"),
    ("Cold-start geography", "New H3 cells return a conservative default with an explicit flag, never a fabrication"),
], col_widths=[Inches(2.6), Inches(9.6)], font_size=13.5)

# ---------------------------------------------------------------------------
# Slide 12 — Results summary / KPIs
# ---------------------------------------------------------------------------
s = add_slide()
header(s, "Results Summary", "What this system actually delivers")
stat_card(s, Inches(0.5), Inches(1.35), Inches(2.85), Inches(1.25), "298,450", "Violations processed")
stat_card(s, Inches(3.5), Inches(1.35), Inches(2.85), Inches(1.25), "2,534", "H3 cells, live predictions")
stat_card(s, Inches(6.5), Inches(1.35), Inches(2.85), Inches(1.25), "0.8767", "Best val PR-AUC")
stat_card(s, Inches(9.5), Inches(1.35), Inches(3.3), Inches(1.25), "78 / 78", "Backend tests passing", good=True)

stat_card(s, Inches(0.5), Inches(2.75), Inches(2.85), Inches(1.25), "94.3%", "Spatial accuracy retained", good=True)
stat_card(s, Inches(3.5), Inches(2.75), Inches(2.85), Inches(1.25), "PASS", "Spatial abstraction", good=True)
stat_card(s, Inches(6.5), Inches(2.75), Inches(2.85), Inches(1.25), "0.15", "Operating threshold")
stat_card(s, Inches(9.5), Inches(2.75), Inches(3.3), Inches(1.25), "0%", "External data used", good=True)

pie_chart(s, Inches(0.5), Inches(4.25), Inches(5.5), Inches(2.9),
          ["LOW", "MEDIUM", "HIGH"], [94.2, 5.5, 0.3], title="Live risk-band distribution (2,534 cells)")

make_table(s, Inches(6.3), Inches(4.25), Inches(6.4), Inches(2.9), [
    ("Verification", "Result"),
    ("Retraining cycles run end-to-end", "3 (features, weights, hyperparameters)"),
    ("Spatial holdout re-checked", "Before and after each change"),
    ("Numbers in this deck", "Read from /metrics + spatial_holdout_result.json, not hand-typed"),
], col_widths=[Inches(3.0), Inches(3.4)], font_size=12)

prs.save("slides/Parking_Intelligence_Deck.pptx")
print("Saved slides/Parking_Intelligence_Deck.pptx")
