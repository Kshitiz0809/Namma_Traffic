"""
Secondary objective: regression on `target_count_60m` — "how severe will
hotspot activity become?" Same model order (CatBoost -> LightGBM -> XGBoost),
same feature set/split as the primary classifier, lighter metric set
(MAE/RMSE/R2 — these are regression metrics; PR-AUC/precision/recall/F1/
calibration don't apply to a count target).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

from app.models.classifier import RANDOM_SEED
from app.models.feature_set import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from app.models.split import TimeSplit


@dataclass
class RegressionMetrics:
    model_name: str
    mae: float
    rmse: float
    r2: float
    n_samples: int

    def to_dict(self) -> dict:
        return {
            "model": self.model_name,
            "mae": round(self.mae, 4),
            "rmse": round(self.rmse, 4),
            "r2": round(self.r2, 4),
            "n_samples": self.n_samples,
        }


def evaluate_regressor(model_name: str, y_true: np.ndarray, y_pred: np.ndarray) -> RegressionMetrics:
    return RegressionMetrics(
        model_name=model_name,
        mae=mean_absolute_error(y_true, y_pred),
        rmse=mean_squared_error(y_true, y_pred) ** 0.5,
        r2=r2_score(y_true, y_pred),
        n_samples=len(y_true),
    )


def train_all_regressors(
    split: TimeSplit,
    target_col: str = "target_count_60m",
    numeric_features: list[str] = NUMERIC_FEATURES,
    categorical_features: list[str] = CATEGORICAL_FEATURES,
) -> dict:
    feature_cols = numeric_features + categorical_features
    X_train, y_train = split.train[feature_cols], split.train[target_col].to_numpy()
    X_val, y_val = split.val[feature_cols], split.val[target_col].to_numpy()

    results = {}

    cb_model = CatBoostRegressor(
        iterations=300, depth=6, learning_rate=0.1,
        cat_features=categorical_features, random_seed=RANDOM_SEED, verbose=False,
    )
    cb_model.fit(X_train, y_train)
    results["catboost"] = {
        "model": cb_model,
        "val_metrics": evaluate_regressor("catboost", y_val, cb_model.predict(X_val)),
    }

    lgb_model = LGBMRegressor(n_estimators=300, max_depth=6, learning_rate=0.1, random_state=RANDOM_SEED, verbose=-1)
    lgb_model.fit(X_train, y_train, categorical_feature=categorical_features)
    results["lightgbm"] = {
        "model": lgb_model,
        "val_metrics": evaluate_regressor("lightgbm", y_val, lgb_model.predict(X_val)),
    }

    xgb_model = XGBRegressor(
        n_estimators=300, max_depth=6, learning_rate=0.1,
        enable_categorical=True, tree_method="hist", random_state=RANDOM_SEED,
    )
    xgb_model.fit(X_train, y_train)
    results["xgboost"] = {
        "model": xgb_model,
        "val_metrics": evaluate_regressor("xgboost", y_val, xgb_model.predict(X_val)),
    }

    return results
