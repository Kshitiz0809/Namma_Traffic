"""Phase 9 tests: lead_time.py — synthetic per-cell time series with known answers."""

import numpy as np
import pandas as pd

from app.models.lead_time import run_lead_time_backtest


def _df(rows):
    df = pd.DataFrame(rows)
    df["created_datetime"] = pd.to_datetime(df["created_datetime"], utc=True)
    return df


def test_episode_caught_30_minutes_early():
    val_df = _df([
        {"h3_cell": "c1", "created_datetime": "2024-01-01 10:00:00", "target_hotspot_60m": 0},
        {"h3_cell": "c1", "created_datetime": "2024-01-01 10:30:00", "target_hotspot_60m": 0},  # probability crosses here
        {"h3_cell": "c1", "created_datetime": "2024-01-01 11:00:00", "target_hotspot_60m": 1},  # episode starts here
    ])
    probabilities = np.array([0.05, 0.20, 0.30])
    result = run_lead_time_backtest(val_df, probabilities)
    assert result.n_episodes == 1
    assert result.n_caught == 1
    assert result.n_missed == 0
    assert result.mean_lead_time_minutes == 30.0


def test_episode_missed_when_probability_never_crosses_threshold():
    val_df = _df([
        {"h3_cell": "c1", "created_datetime": "2024-01-01 10:00:00", "target_hotspot_60m": 0},
        {"h3_cell": "c1", "created_datetime": "2024-01-01 11:00:00", "target_hotspot_60m": 1},
    ])
    probabilities = np.array([0.05, 0.10])  # never reaches the 0.15 threshold
    result = run_lead_time_backtest(val_df, probabilities)
    assert result.n_caught == 0
    assert result.n_missed == 1


def test_crossing_outside_lookback_window_does_not_count():
    val_df = _df([
        {"h3_cell": "c1", "created_datetime": "2024-01-01 06:00:00", "target_hotspot_60m": 0},  # 5h before episode -- outside 3h lookback
        {"h3_cell": "c1", "created_datetime": "2024-01-01 11:00:00", "target_hotspot_60m": 1},
    ])
    probabilities = np.array([0.50, 0.05])
    result = run_lead_time_backtest(val_df, probabilities)
    assert result.n_caught == 0
    assert result.n_missed == 1


def test_no_episodes_in_an_all_negative_cell():
    val_df = _df([
        {"h3_cell": "c1", "created_datetime": "2024-01-01 10:00:00", "target_hotspot_60m": 0},
        {"h3_cell": "c1", "created_datetime": "2024-01-01 11:00:00", "target_hotspot_60m": 0},
    ])
    probabilities = np.array([0.05, 0.05])
    result = run_lead_time_backtest(val_df, probabilities)
    assert result.n_episodes == 0
    assert result.n_caught == 0
    assert result.n_missed == 0


def test_multiple_cells_and_episodes_aggregate_correctly():
    val_df = _df([
        {"h3_cell": "c1", "created_datetime": "2024-01-01 10:00:00", "target_hotspot_60m": 0},
        {"h3_cell": "c1", "created_datetime": "2024-01-01 10:45:00", "target_hotspot_60m": 0},
        {"h3_cell": "c1", "created_datetime": "2024-01-01 11:00:00", "target_hotspot_60m": 1},  # +15min lead
        {"h3_cell": "c2", "created_datetime": "2024-01-01 10:00:00", "target_hotspot_60m": 0},
        {"h3_cell": "c2", "created_datetime": "2024-01-01 10:00:00", "target_hotspot_60m": 0},
        {"h3_cell": "c2", "created_datetime": "2024-01-01 11:00:00", "target_hotspot_60m": 1},  # +60min lead
    ])
    probabilities = np.array([0.05, 0.20, 0.30, 0.05, 0.20, 0.30])
    result = run_lead_time_backtest(val_df, probabilities)
    assert result.n_episodes == 2
    assert result.n_caught == 2
    assert result.mean_lead_time_minutes == pytest_approx_mean([15.0, 60.0])


def pytest_approx_mean(values):
    return round(sum(values) / len(values), 1)
