"""
Generates architecture_diagram.png and system_flow.png for Phase 6 Task 5
(presentation assets). Plain matplotlib boxes/arrows — no graphviz
dependency, consistent with the project's existing matplotlib-based
notebook plots. Run: `python _generate_diagrams.py` from docs/.
"""

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

PHASE_COLOR = "#3b6ea5"
MODEL_COLOR = "#5a9367"
SERVE_COLOR = "#c97a3d"
UI_COLOR = "#9c5fa8"
DATA_COLOR = "#6b7280"


def box(ax, xy, w, h, text, color, fontsize=9.5, text_color="white"):
    rect = mpatches.FancyBboxPatch(
        xy, w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=0, facecolor=color,
    )
    ax.add_patch(rect)
    ax.text(
        xy[0] + w / 2, xy[1] + h / 2, text,
        ha="center", va="center", fontsize=fontsize, color=text_color, wrap=True,
    )


def arrow(ax, start, end, color="#374151"):
    ax.annotate(
        "", xy=end, xytext=start,
        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.6, shrinkA=2, shrinkB=2),
    )


def architecture_diagram():
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title(
        "Parking Intelligence + Predictive Alert Platform — Architecture",
        fontsize=14, fontweight="bold", pad=14,
    )

    # Row 1: data + ingestion
    box(ax, (0.3, 6.6), 2.6, 0.9, "Raw CSV\n298,450 rows\n(internal-only, ADR-001)", DATA_COLOR)
    box(ax, (3.3, 6.6), 2.6, 0.9, "Ingestion +\nSchema Validation\n(Phase 1)", PHASE_COLOR)
    box(ax, (6.3, 6.6), 2.8, 0.9, "Feature Engineering\nH3, rolling, historical-risk\n(Phase 2 — FROZEN)", PHASE_COLOR)
    box(ax, (9.5, 6.6), 3.1, 0.9, "features.parquet\ntargets.parquet", DATA_COLOR)

    arrow(ax, (2.9, 7.05), (3.3, 7.05))
    arrow(ax, (5.9, 7.05), (6.3, 7.05))
    arrow(ax, (9.1, 7.05), (9.5, 7.05))

    # Row 2: modeling
    box(ax, (0.3, 4.9), 3.0, 0.9, "CatBoost / LightGBM\n/ XGBoost (Phase 3)\nwinner: CatBoost", MODEL_COLOR)
    box(ax, (3.6, 4.9), 2.8, 0.9, "Hardening (Phase 3.5)\nthreshold 0.15, calibration,\nspatial holdout (FAIL)", MODEL_COLOR)
    box(ax, (6.7, 4.9), 2.6, 0.9, "Multi-horizon +\nfeature lock (Phase 4)\n60min, ADR-019 FROZEN", MODEL_COLOR)
    box(ax, (9.6, 4.9), 3.0, 0.9, "ml/models/\n*.cbm *.txt *.json\n(frozen artifacts)", DATA_COLOR)

    arrow(ax, (10.9, 6.6), (10.9, 5.8))
    arrow(ax, (3.3, 5.35), (3.6, 5.35))
    arrow(ax, (6.4, 5.35), (6.7, 5.35))
    arrow(ax, (9.3, 5.35), (9.6, 5.35))

    # Row 3: risk/recommendation/alert layer
    box(ax, (0.3, 3.2), 2.9, 0.9, "risk_score\n(derived, NOT trained)\nPhase 5", SERVE_COLOR)
    box(ax, (3.5, 3.2), 2.9, 0.9, "recommendation_rules.yaml\n(rule-based, no LLM)", SERVE_COLOR)
    box(ax, (6.7, 3.2), 2.9, 0.9, "Alert Layer\nGREEN/YELLOW/ORANGE/RED", SERVE_COLOR)

    arrow(ax, (11.1, 4.9), (1.7, 4.1))
    arrow(ax, (3.2, 3.65), (3.5, 3.65))
    arrow(ax, (6.4, 3.65), (6.7, 3.65))

    # Row 4: API
    box(ax, (1.0, 1.6), 3.6, 0.9, "FastAPI\n/forecast /alerts /metrics /health\n(Phase 6 — CORS enabled)", PHASE_COLOR)
    arrow(ax, (2.1, 3.2), (2.6, 2.5))
    arrow(ax, (8.1, 3.2), (3.3, 2.5))

    # Row 5: clients/deployment
    box(ax, (0.3, 0.1), 3.2, 0.9, "Next.js + Leaflet\nDashboard (Vercel)", UI_COLOR)
    box(ax, (4.0, 0.1), 3.2, 0.9, "demo_seed.py\n(replay/growth/recs)", UI_COLOR)
    box(ax, (7.7, 0.1), 3.0, 0.9, "Backend on Render\n(prepared, not deployed)", UI_COLOR)

    arrow(ax, (1.9, 1.6), (1.9, 1.0))
    arrow(ax, (2.8, 1.6), (5.6, 1.0))
    arrow(ax, (4.6, 1.6), (9.2, 1.0))

    plt.tight_layout()
    plt.savefig("architecture_diagram.png", dpi=130)
    plt.close(fig)
    print("Wrote architecture_diagram.png")


def system_flow_diagram():
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 5.5)
    ax.axis("off")
    ax.set_title(
        "Request Flow — GET /forecast?h3_cell=...",
        fontsize=14, fontweight="bold", pad=14,
    )

    steps = [
        (0.3, "Dashboard\n(Forecast Panel)", UI_COLOR),
        (2.5, "FastAPI\n/forecast", PHASE_COLOR),
        (4.7, "Latest snapshot\nlookup per H3 cell\n(idxmax, no full sort)", DATA_COLOR),
        (6.9, "Frozen CatBoost\nclassifier + regressor\n(no retraining)", MODEL_COLOR),
        (9.1, "risk_score +\nrecommendation engine", SERVE_COLOR),
    ]
    y = 3.0
    w, h = 2.0, 1.3
    for x, label, color in steps:
        box(ax, (x, y), w, h, label, color, fontsize=9)

    for i in range(len(steps) - 1):
        x1 = steps[i][0] + w
        x2 = steps[i + 1][0]
        arrow(ax, (x1, y + h / 2), (x2, y + h / 2))

    # Response path (dashed, going back)
    ax.annotate(
        "", xy=(steps[0][0] + w / 2, y - 0.1), xytext=(steps[-1][0] + w / 2, y - 0.6),
        arrowprops=dict(arrowstyle="-|>", color="#9ca3af", lw=1.4, linestyle="dashed",
                         connectionstyle="arc3,rad=-0.3"),
    )
    ax.text(6, 1.0, "JSON response: hotspot_probability, predicted_count,\n"
                     "congestion_risk, risk_band, recommendation, confidence",
            ha="center", fontsize=9.5, color="#374151")

    ax.text(6, 0.2,
            "Cold start (unseen H3 cell) -> conservative default response, not a fabricated prediction (ADR-016)",
            ha="center", fontsize=8.5, color="#b91c1c", style="italic")

    plt.tight_layout()
    plt.savefig("system_flow.png", dpi=130)
    plt.close(fig)
    print("Wrote system_flow.png")


if __name__ == "__main__":
    architecture_diagram()
    system_flow_diagram()
