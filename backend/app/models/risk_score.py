"""
Phase 5 Task 1 — Parking-Induced Congestion Risk score.

NOT a new ML target (explicit instruction) — a derived score computed from
the FROZEN Phase 3 model outputs + existing leakage-safe features, exactly
like `congestion_score.py` (Phase 3, ADR-011) but using model PREDICTIONS
as inputs rather than raw features only. Kept as a separate module from
`congestion_score.py` because the two formulas serve different purposes and
have different inputs — not a replacement, an addition.

    risk_score = 100 * (
        0.40 * hotspot_probability          (from the frozen classifier)
      + 0.30 * normalized_predicted_count   (from the frozen regressor, min-max scaled)
      + 0.20 * persistence                  (from rolling_hotspot_intensity, min-max scaled)
      + 0.10 * recent_intensity             (from violations_last_15m, min-max scaled)
    )

All min-max scaling is fit on the TRAIN period only (same leakage-safety
discipline as ADR-011) and clipped, not extrapolated, for rows outside that
range.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

WEIGHTS = {
    "hotspot_probability": 0.40,
    "normalized_predicted_count": 0.30,
    "persistence": 0.20,
    "recent_intensity": 0.10,
}

# Risk bands — DATA-DRIVEN, not arbitrary round numbers. Fixed cutoffs at
# 40/60/80 were tried first and left the CRITICAL band essentially empty
# (the real score distribution tops out around 65-82, not 100, because the
# 4 weighted components rarely all peak simultaneously). These cutoffs are
# the 50th/85th/97th percentiles of risk_score computed on the TRAIN period
# (leakage-safe, same discipline as the min-max scaling above) — see
# risk_definition.md for the derivation and resulting band populations.
RISK_BANDS = [
    (0, 34.0, "LOW"),        # ~50th percentile
    (34.0, 45.1, "MEDIUM"),  # ~85th percentile
    (45.1, 54.2, "HIGH"),    # ~97th percentile
    (54.2, 1000.0, "CRITICAL"),  # top ~3%
]


@dataclass
class RiskMinMaxParams:
    predicted_count_min: float
    predicted_count_max: float
    rolling_intensity_min: float
    rolling_intensity_max: float
    recent_intensity_min: float
    recent_intensity_max: float


def fit_risk_minmax(train_predicted_count: pd.Series, train_features: pd.DataFrame) -> RiskMinMaxParams:
    return RiskMinMaxParams(
        predicted_count_min=float(train_predicted_count.min()),
        predicted_count_max=float(train_predicted_count.max()),
        rolling_intensity_min=float(train_features["rolling_hotspot_intensity"].min()),
        rolling_intensity_max=float(train_features["rolling_hotspot_intensity"].max()),
        recent_intensity_min=float(train_features["violations_last_15m"].min()),
        recent_intensity_max=float(train_features["violations_last_15m"].max()),
    )


def _scale(series: pd.Series, lo: float, hi: float) -> pd.Series:
    if hi <= lo:
        return pd.Series(0.0, index=series.index)
    return ((series - lo) / (hi - lo)).clip(0.0, 1.0)


def compute_risk_score(
    hotspot_probability: np.ndarray,
    predicted_count: np.ndarray,
    features: pd.DataFrame,
    params: RiskMinMaxParams,
) -> pd.DataFrame:
    """Returns a DataFrame with the 4 weighted components + final risk_score
    (0-100) + risk_band, indexed like `features`.
    """
    out = pd.DataFrame(index=features.index)
    out["hotspot_probability"] = hotspot_probability
    out["normalized_predicted_count"] = _scale(
        pd.Series(predicted_count, index=features.index), params.predicted_count_min, params.predicted_count_max
    )
    out["persistence"] = _scale(
        features["rolling_hotspot_intensity"], params.rolling_intensity_min, params.rolling_intensity_max
    )
    out["recent_intensity"] = _scale(
        features["violations_last_15m"], params.recent_intensity_min, params.recent_intensity_max
    )

    weighted_sum = sum(WEIGHTS[c] * out[c] for c in WEIGHTS)
    out["risk_score"] = (weighted_sum * 100).round(2)
    out["risk_band"] = out["risk_score"].apply(assign_risk_band)

    # Per-component weighted contribution (used for "top contributing
    # factors" in the alert layer, Task 3) — same components, scaled by
    # their weight, so they're directly comparable to each other.
    for c in WEIGHTS:
        out[f"contribution_{c}"] = WEIGHTS[c] * out[c] * 100

    return out


def assign_risk_band(score: float) -> str:
    for lo, hi, band in RISK_BANDS:
        if lo <= score < hi:
            return band
    return "CRITICAL"  # score == 100 edge case
