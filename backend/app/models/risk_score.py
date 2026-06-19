"""
Phase 5 Task 1 — Parking-Induced Congestion Risk score.

NOT a new ML target (explicit instruction) — a derived score computed from
the model outputs + existing leakage-safe features, exactly like
`congestion_score.py` (Phase 3, ADR-011) but using model PREDICTIONS as
inputs rather than raw features only. Kept as a separate module from
`congestion_score.py` because the two formulas serve different purposes and
have different inputs — not a replacement, an addition.

    risk_score = 100 * (
        w_hotspot * hotspot_probability          (from the classifier)
      + w_count   * normalized_predicted_count   (from the regressor, min-max scaled)
      + w_persist * persistence                  (from rolling_hotspot_intensity, min-max scaled)
      + w_recent  * recent_intensity             (from violations_last_15m, min-max scaled)
    )

ADR-021: weights, band cutoffs, and min-max scale params are no longer
hand-picked literals baked into source — they're FIT on the train split
(`fit_risk_params`) every time the model retrains, and persisted to
`ml/models/risk_params.json` (`RiskParams`), loaded by the serving layer.
This closes the "weights are a guess" gap: there's still no ground-truth
congestion data in the provided dataset, so `target_count_60m` (actual
realized violation count in the next 60 minutes) is used as the best
available outcome proxy to fit `fit_risk_weights` against — an honest
proxy-fit, not a measured causal weight, but data-driven rather than
arbitrary. All fitting happens on the TRAIN period only (same
leakage-safety discipline as ADR-011) and is clipped, not extrapolated,
for rows outside that range at serving time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import nnls

COMPONENT_NAMES = ["hotspot_probability", "normalized_predicted_count", "persistence", "recent_intensity"]

# Fallback only used if NNLS degenerates (e.g. zero-variance outcome on a
# tiny/synthetic train slice) — equal weights, not the old hand-picked ones.
_FALLBACK_WEIGHTS = {name: 1.0 / len(COMPONENT_NAMES) for name in COMPONENT_NAMES}


@dataclass
class RiskParams:
    weights: dict[str, float]
    # 3 ascending cutoffs (50th/85th/97th percentile of train-period risk
    # scores, same discipline as the old hardcoded RISK_BANDS) -> 4 bands:
    # LOW/MEDIUM/HIGH/CRITICAL.
    band_cutoffs: list[float] = field(default_factory=lambda: [34.0, 45.1, 54.2])
    predicted_count_min: float = 0.0
    predicted_count_max: float = 1.0
    rolling_intensity_min: float = 0.0
    rolling_intensity_max: float = 1.0
    recent_intensity_min: float = 0.0
    recent_intensity_max: float = 1.0


def _scale(series: pd.Series, lo: float, hi: float) -> pd.Series:
    if hi <= lo:
        return pd.Series(0.0, index=series.index)
    return ((series - lo) / (hi - lo)).clip(0.0, 1.0)


def fit_risk_minmax(train_predicted_count: pd.Series, train_features: pd.DataFrame) -> dict[str, float]:
    return {
        "predicted_count_min": float(pd.Series(train_predicted_count).min()),
        "predicted_count_max": float(pd.Series(train_predicted_count).max()),
        "rolling_intensity_min": float(train_features["rolling_hotspot_intensity"].min()),
        "rolling_intensity_max": float(train_features["rolling_hotspot_intensity"].max()),
        "recent_intensity_min": float(train_features["violations_last_15m"].min()),
        "recent_intensity_max": float(train_features["violations_last_15m"].max()),
    }


def _raw_components(
    hotspot_probability: np.ndarray,
    predicted_count: np.ndarray,
    features: pd.DataFrame,
    minmax: dict[str, float],
) -> pd.DataFrame:
    index = features.index
    return pd.DataFrame({
        "hotspot_probability": np.asarray(hotspot_probability, dtype=float),
        "normalized_predicted_count": _scale(
            pd.Series(np.asarray(predicted_count, dtype=float), index=index),
            minmax["predicted_count_min"], minmax["predicted_count_max"],
        ).to_numpy(),
        "persistence": _scale(
            features["rolling_hotspot_intensity"], minmax["rolling_intensity_min"], minmax["rolling_intensity_max"],
        ).to_numpy(),
        "recent_intensity": _scale(
            features["violations_last_15m"], minmax["recent_intensity_min"], minmax["recent_intensity_max"],
        ).to_numpy(),
    }, index=index)


# Ridge penalty candidates tried smallest-first; the smallest alpha that
# keeps every component's weight at or below this share is kept. Plain NNLS
# (alpha=0) reliably collapses to ~100% on normalized_predicted_count below
# (the regressor was LITERALLY trained to predict target_count_60m, so
# regressing that same target on its own prediction is near-tautological —
# the other 3 components get zeroed out, which defeats the point of a
# composite score and makes "top contributing factors" meaningless). Ridge
# regularization is the standard fix for a NNLS fit collapsing onto one of
# several correlated predictors (components.corr() shows 0.48-0.63
# correlation between all 4) — it trades a small amount of raw fit quality
# for a weight distribution that still reflects genuine signal in all 4
# components, not just whichever one is closest to the fitting target.
_RIDGE_ALPHA_CANDIDATES = [0.0, 10.0, 50.0, 100.0, 200.0, 500.0, 1000.0, 2000.0, 5000.0]
_MAX_SINGLE_COMPONENT_SHARE = 0.75


def _nnls_ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """NNLS with an L2 penalty, via the standard augmented-system trick:
    appending sqrt(alpha)*I rows to X and zero rows to y penalizes large
    coefficients exactly like ridge regression, while keeping the
    non-negativity constraint NNLS provides.
    """
    if alpha == 0.0:
        coeffs, _residual = nnls(X, y)
        return coeffs
    n_features = X.shape[1]
    X_aug = np.vstack([X, np.sqrt(alpha) * np.eye(n_features)])
    y_aug = np.concatenate([y, np.zeros(n_features)])
    coeffs, _residual = nnls(X_aug, y_aug)
    return coeffs


def fit_risk_weights(
    hotspot_probability: np.ndarray,
    predicted_count: np.ndarray,
    features: pd.DataFrame,
    outcome: pd.Series,
    minmax: dict[str, float],
) -> dict[str, float]:
    """Ridge-regularized, non-negativity-constrained regression of the 4 raw
    risk components against `outcome` (the realized next-60-minute violation
    count, `target_count_60m`, on the TRAIN split) — the closest available
    outcome proxy for "actual impact" in a dataset with no ground-truth
    congestion data. Coefficients are normalized to sum to 1 so the result
    is directly comparable to the old hand-picked WEIGHTS dict.

    Searches `_RIDGE_ALPHA_CANDIDATES` smallest-first and keeps the first
    fit where no single component exceeds `_MAX_SINGLE_COMPONENT_SHARE` of
    the total weight — the smallest regularization strength sufficient to
    avoid collapsing onto one predictor, rather than an arbitrarily large
    fixed alpha.
    """
    components = _raw_components(hotspot_probability, predicted_count, features, minmax)
    X = components.to_numpy()
    y = np.asarray(outcome, dtype=float)

    best_normalized = None
    for alpha in _RIDGE_ALPHA_CANDIDATES:
        coeffs = _nnls_ridge(X, y, alpha)
        total = coeffs.sum()
        if total <= 0:
            continue
        normalized = coeffs / total
        best_normalized = normalized
        if normalized.max() <= _MAX_SINGLE_COMPONENT_SHARE:
            break

    if best_normalized is None:
        return dict(_FALLBACK_WEIGHTS)
    return dict(zip(COMPONENT_NAMES, best_normalized.tolist()))


def fit_risk_bands(risk_scores: pd.Series) -> list[float]:
    """50th/85th/97th percentile cutoffs of TRAIN-period risk scores — same
    "why not round numbers" rationale as the original hardcoded RISK_BANDS:
    fixed cutoffs at 40/60/80 leave the CRITICAL band nearly empty because
    the 4 weighted components rarely all peak simultaneously.
    """
    return [float(risk_scores.quantile(q)) for q in (0.50, 0.85, 0.97)]


def fit_risk_params(
    hotspot_probability: np.ndarray,
    predicted_count: np.ndarray,
    features: pd.DataFrame,
    outcome: pd.Series,
) -> RiskParams:
    """One-shot fit of everything risk-score-related (weights, min-max scale,
    band cutoffs) on the same train-period rows — called once per retrain
    from `train.run()`, replacing the old separately-hardcoded WEIGHTS/
    RISK_BANDS module constants and the old standalone `fit_risk_minmax`
    call site.
    """
    minmax = fit_risk_minmax(pd.Series(predicted_count), features)
    weights = fit_risk_weights(hotspot_probability, predicted_count, features, outcome, minmax)

    components = _raw_components(hotspot_probability, predicted_count, features, minmax)
    prelim_scores = (sum(weights[c] * components[c] for c in COMPONENT_NAMES) * 100)
    band_cutoffs = fit_risk_bands(prelim_scores)

    return RiskParams(weights=weights, band_cutoffs=band_cutoffs, **minmax)


def assign_risk_band(score: float, band_cutoffs: list[float]) -> str:
    lo, mid, hi = band_cutoffs
    if score < lo:
        return "LOW"
    if score < mid:
        return "MEDIUM"
    if score < hi:
        return "HIGH"
    return "CRITICAL"


def compute_risk_score(
    hotspot_probability: np.ndarray,
    predicted_count: np.ndarray,
    features: pd.DataFrame,
    params: RiskParams,
) -> pd.DataFrame:
    """Returns a DataFrame with the 4 weighted components + final risk_score
    (0-100) + risk_band, indexed like `features`.
    """
    minmax = {
        "predicted_count_min": params.predicted_count_min,
        "predicted_count_max": params.predicted_count_max,
        "rolling_intensity_min": params.rolling_intensity_min,
        "rolling_intensity_max": params.rolling_intensity_max,
        "recent_intensity_min": params.recent_intensity_min,
        "recent_intensity_max": params.recent_intensity_max,
    }
    out = _raw_components(hotspot_probability, predicted_count, features, minmax)

    weighted_sum = sum(params.weights[c] * out[c] for c in COMPONENT_NAMES)
    out["risk_score"] = (weighted_sum * 100).round(2)
    out["risk_band"] = out["risk_score"].apply(lambda s: assign_risk_band(s, params.band_cutoffs))

    # Per-component weighted contribution (used for "top contributing
    # factors" in the alert layer, Task 3) — same components, scaled by
    # their weight, so they're directly comparable to each other.
    for c in COMPONENT_NAMES:
        out[f"contribution_{c}"] = params.weights[c] * out[c] * 100

    return out
