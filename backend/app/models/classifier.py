"""
Primary objective (per user's Phase 3 scope adjustment): binary classifier
for `target_hotspot_60m` — "will this H3 area become a hotspot in the next
60 minutes?" Trains CatBoost -> LightGBM -> XGBoost on the same data/split
and reports the same metrics for a fair comparison (DECISIONS.md ADR-008).

Categorical dtype consistency note: `prepare_model_frame` (feature_set.py)
must be called on the FULL dataset before splitting, not per-split — pandas
'category' dtype codes are assigned per-Series, so casting train/val/test
separately could give the same category different integer codes in each
split, silently corrupting LightGBM/XGBoost (which both rely on category
codes). CatBoost isn't affected (it encodes from raw values, not pandas
codes) but we keep one code path for all three models regardless.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from xgboost import XGBClassifier

from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES, prepare_model_frame
from app.models.split import TimeSplit, time_based_split

RANDOM_SEED = 42


@dataclass
class ClassificationMetrics:
    model_name: str
    pr_auc: float
    precision: float
    recall: float
    f1: float
    brier_score: float
    best_threshold: float
    confusion_matrix: list[list[int]] = field(default_factory=list)
    n_samples: int = 0
    positive_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "model": self.model_name,
            "pr_auc": round(self.pr_auc, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "brier_score": round(self.brier_score, 4),
            "best_threshold": round(self.best_threshold, 3),
            "n_samples": self.n_samples,
            "positive_rate": round(self.positive_rate, 4),
            "confusion_matrix": self.confusion_matrix,
        }


def build_classification_dataset(
    features_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    target_col: str = "target_hotspot_60m",
    numeric_features: list[str] = NUMERIC_FEATURES,
    categorical_features: list[str] = CATEGORICAL_FEATURES,
) -> TimeSplit:
    """Merge features + target, cast dtypes ONCE on the full dataset (see
    module docstring), then time-split. Returns a TimeSplit whose .train/
    .val/.test each contain the feature columns + target_col + created_datetime.
    """
    merged = features_df.merge(targets_df[["id", target_col]], on="id")
    model_frame = prepare_model_frame(merged, numeric_features, categorical_features)
    model_frame[target_col] = merged[target_col].to_numpy()
    model_frame["created_datetime"] = merged["created_datetime"].to_numpy()
    return time_based_split(model_frame)


def _find_best_threshold(y_true: np.ndarray, y_proba: np.ndarray) -> float:
    """Threshold that maximizes F1 on the given set, searched over the
    predicted-probability deciles — simple and adequate for a baseline.
    """
    thresholds = np.linspace(0.05, 0.95, 19)
    f1s = [f1_score(y_true, (y_proba >= t).astype(int), zero_division=0) for t in thresholds]
    return float(thresholds[int(np.argmax(f1s))])


def evaluate_classifier(
    model_name: str,
    y_true: np.ndarray,
    y_proba: np.ndarray,
    threshold: float | None = None,
) -> ClassificationMetrics:
    if threshold is None:
        threshold = _find_best_threshold(y_true, y_proba)
    y_pred = (y_proba >= threshold).astype(int)

    return ClassificationMetrics(
        model_name=model_name,
        pr_auc=average_precision_score(y_true, y_proba),
        precision=precision_score(y_true, y_pred, zero_division=0),
        recall=recall_score(y_true, y_pred, zero_division=0),
        f1=f1_score(y_true, y_pred, zero_division=0),
        brier_score=brier_score_loss(y_true, y_proba),
        best_threshold=threshold,
        confusion_matrix=confusion_matrix(y_true, y_pred).tolist(),
        n_samples=len(y_true),
        positive_rate=float(np.mean(y_true)),
    )


def train_catboost(X_train, y_train, categorical_features: list[str]) -> CatBoostClassifier:
    # depth=3 (was 6), l2_leaf_reg=25 (CatBoost default 3) — ADR-025: a
    # depth/L2 sweep against the spatial holdout test (app/models/spatial_holdout.py)
    # found shallower, more-regularized trees reduce the unseen-cell PR-AUC
    # drop from 6.32% to 5.66% while matching or slightly beating the
    # depth=6 default on SEEN-cell accuracy too (0.8792 -> 0.8796) — a
    # strict improvement, not a tradeoff. Going shallower still (depth=2/1)
    # buys a bit more drop reduction but starts costing real seen-cell
    # accuracy; depth=3/l2=25 was the best point with no downside.
    model = CatBoostClassifier(
        iterations=300,
        depth=3,
        learning_rate=0.1,
        l2_leaf_reg=25,
        loss_function="Logloss",
        eval_metric="PRAUC",
        cat_features=categorical_features,
        random_seed=RANDOM_SEED,
        verbose=False,
    )
    model.fit(X_train, y_train)
    return model


def train_lightgbm(X_train, y_train, categorical_features: list[str]) -> LGBMClassifier:
    model = LGBMClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        random_state=RANDOM_SEED,
        verbose=-1,
    )
    model.fit(X_train, y_train, categorical_feature=categorical_features)
    return model


def train_xgboost(X_train, y_train) -> XGBClassifier:
    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        enable_categorical=True,
        tree_method="hist",
        random_state=RANDOM_SEED,
        eval_metric="aucpr",
    )
    model.fit(X_train, y_train)
    return model


def train_all_classifiers(
    split: TimeSplit,
    target_col: str = "target_hotspot_60m",
    numeric_features: list[str] = NUMERIC_FEATURES,
    categorical_features: list[str] = CATEGORICAL_FEATURES,
) -> dict:
    """Trains CatBoost, LightGBM, XGBoost on split.train, evaluates on
    split.val (model selection happens on val, never on test — test is
    touched once, at the very end, by whoever calls this with the winner).
    Returns {model_name: {"model": ..., "val_metrics": ..., "feature_cols": ...}}.
    """
    feature_cols = numeric_features + categorical_features
    X_train, y_train = split.train[feature_cols], split.train[target_col].to_numpy()
    X_val, y_val = split.val[feature_cols], split.val[target_col].to_numpy()

    results = {}

    cb_model = train_catboost(X_train, y_train, categorical_features)
    cb_proba = cb_model.predict_proba(X_val)[:, 1]
    results["catboost"] = {
        "model": cb_model,
        "val_metrics": evaluate_classifier("catboost", y_val, cb_proba),
    }

    lgb_model = train_lightgbm(X_train, y_train, categorical_features)
    lgb_proba = lgb_model.predict_proba(X_val)[:, 1]
    results["lightgbm"] = {
        "model": lgb_model,
        "val_metrics": evaluate_classifier("lightgbm", y_val, lgb_proba),
    }

    xgb_model = train_xgboost(X_train, y_train)
    xgb_proba = xgb_model.predict_proba(X_val)[:, 1]
    results["xgboost"] = {
        "model": xgb_model,
        "val_metrics": evaluate_classifier("xgboost", y_val, xgb_proba),
    }

    return results
