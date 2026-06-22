"""Phase 9 tests: hotspot_trend.py — synthetic cases with known answers."""

import pandas as pd

from app.models.hotspot_trend import classify_hotspot_trend


def test_low_band_is_always_stable_regardless_of_activity():
    violations_last_60m = pd.Series([0, 10, 100])
    violation_density = pd.Series([1.0, 1.0, 1.0])
    risk_band = pd.Series(["LOW", "LOW", "LOW"])
    out = classify_hotspot_trend(violations_last_60m, violation_density, risk_band)
    assert (out == "STABLE").all()


def test_elevated_band_with_recent_activity_matching_history_is_steady():
    # 1 violation in the last 60m -> 24/day equivalent, matches a 24/day historical rate.
    violations_last_60m = pd.Series([1.0])
    violation_density = pd.Series([24.0])
    risk_band = pd.Series(["HIGH"])
    out = classify_hotspot_trend(violations_last_60m, violation_density, risk_band)
    assert out.iloc[0] == "STEADY"


def test_elevated_band_with_recent_spike_well_above_history_is_emerging():
    # 5 violations in the last 60m -> 120/day equivalent, vs. a 10/day historical rate (12x).
    violations_last_60m = pd.Series([5.0])
    violation_density = pd.Series([10.0])
    risk_band = pd.Series(["CRITICAL"])
    out = classify_hotspot_trend(violations_last_60m, violation_density, risk_band)
    assert out.iloc[0] == "EMERGING"


def test_elevated_band_with_no_history_and_current_activity_is_emerging():
    # Brand-new pattern: cell has almost no historical density but is active right now.
    violations_last_60m = pd.Series([1.0])
    violation_density = pd.Series([0.0])
    risk_band = pd.Series(["MEDIUM"])
    out = classify_hotspot_trend(violations_last_60m, violation_density, risk_band)
    assert out.iloc[0] == "EMERGING"


def test_elevated_band_with_no_history_and_no_current_activity_is_steady():
    violations_last_60m = pd.Series([0.0])
    violation_density = pd.Series([0.0])
    risk_band = pd.Series(["MEDIUM"])
    out = classify_hotspot_trend(violations_last_60m, violation_density, risk_band)
    assert out.iloc[0] == "STEADY"
