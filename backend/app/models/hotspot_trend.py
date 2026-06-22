"""
Phase 9 — emerging vs. steady-state hotspot classification (ADR-026).

A cell flagged HIGH/CRITICAL risk could mean two very different things
operationally: a chronic problem area police already know about
(steady-state), or a brand-new spike that just started (emerging) — the
second is where a patrol redirect actually changes the outcome, since
steady-state hotspots are presumably already part of routine patrol
patterns.

Built entirely from features that already exist in the trained feature
set — no new model trained. Compares a SHORT-TERM rate
(`violations_last_60m`, extrapolated to a daily-equivalent rate) against
the cell's own LONG-RUN historical rate (`violation_density`, violations/
day since the cell's first recorded violation). A ratio well above 1
means "recent activity far exceeds this cell's own historical norm" — a
cell-relative signal, not an absolute count that would unfairly flag
naturally busy junctions as "emerging" forever.
"""

from __future__ import annotations

import pandas as pd

EMERGING_RATIO_THRESHOLD = 2.0
# Below this daily rate, a cell has too little history to compute a stable
# ratio — treat any current activity at all as a meaningful new signal.
MIN_BASELINE_DENSITY = 0.5
ELEVATED_BANDS = ("MEDIUM", "HIGH", "CRITICAL")


def classify_hotspot_trend(
    violations_last_60m: pd.Series,
    violation_density: pd.Series,
    risk_band: pd.Series,
) -> pd.Series:
    """Returns one of EMERGING / STEADY / STABLE per row.

    EMERGING: risk_band is MEDIUM+ and recent activity is at least
        EMERGING_RATIO_THRESHOLD x this cell's own historical daily rate
        (or the cell has too little history to have a stable baseline at
        all, and is already showing activity right now).
    STEADY: risk_band is MEDIUM+ but recent activity is in line with (or
        below) this cell's own history — a known, chronic risk area.
    STABLE: risk_band is LOW.
    """
    recent_daily_rate = violations_last_60m.astype(float) * 24.0
    low_history = violation_density < MIN_BASELINE_DENSITY
    ratio = recent_daily_rate / violation_density.clip(lower=MIN_BASELINE_DENSITY)

    is_elevated = risk_band.isin(ELEVATED_BANDS)
    is_emerging = is_elevated & (
        (ratio >= EMERGING_RATIO_THRESHOLD) | (low_history & (violations_last_60m > 0))
    )

    trend = pd.Series("STABLE", index=violations_last_60m.index)
    trend[is_elevated] = "STEADY"
    trend[is_emerging] = "EMERGING"
    return trend
