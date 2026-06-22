"""
Phase 9 — backtested early-warning lead time (ADR-026).

Quantifies "how many minutes before a real hotspot forms would this
system have flagged it" — not a property of any single prediction (the
60-minute horizon is baked into the target's own definition), but
genuinely BACKTESTED by replaying the validation period chronologically
per H3 cell and finding, for each real hotspot episode (a transition from
target_hotspot_60m=0 to =1), the earliest point within a bounded lookback
window at which the classifier's predicted probability had already
crossed the operating threshold. That earliest-crossing timestamp can be
well before the episode itself even starts accumulating, since the
classifier reacts to leading indicators (recent rate of change, junction
history), not just the raw count that defines the label.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

LOOKBACK_MINUTES = 180  # don't credit a crossing more than 3h before episode start as "the" warning
OPERATING_THRESHOLD = 0.15


@dataclass
class LeadTimeResult:
    n_episodes: int
    n_caught: int
    n_missed: int
    mean_lead_time_minutes: float
    median_lead_time_minutes: float
    pct_caught_30m_plus: float
    pct_caught_60m_plus: float
    lead_time_samples_minutes: list[float] = field(default_factory=list)


def run_lead_time_backtest(
    val_df: pd.DataFrame,
    probabilities: np.ndarray,
    target_col: str = "target_hotspot_60m",
    cell_col: str = "h3_cell",
    time_col: str = "created_datetime",
) -> LeadTimeResult:
    df = val_df[[cell_col, time_col, target_col]].copy()
    df["probability"] = np.asarray(probabilities)
    df = df.sort_values([cell_col, time_col]).reset_index(drop=True)

    lead_times: list[float] = []
    n_missed = 0

    for _, group in df.groupby(cell_col):
        group = group.reset_index(drop=True)
        labels = group[target_col].to_numpy()
        if len(labels) == 0:
            continue
        prev = np.concatenate([[0], labels[:-1]])
        episode_starts = np.where((labels == 1) & (prev == 0))[0]
        if len(episode_starts) == 0:
            continue

        times = group[time_col].to_numpy()
        probs = group["probability"].to_numpy()

        for idx in episode_starts:
            episode_time = times[idx]
            lookback_start = episode_time - np.timedelta64(LOOKBACK_MINUTES, "m")
            window_mask = (times >= lookback_start) & (times <= episode_time)
            window_idx = np.where(window_mask)[0]
            crossed = window_idx[probs[window_idx] >= OPERATING_THRESHOLD]
            if len(crossed) == 0:
                n_missed += 1
                continue
            first_cross_time = times[crossed[0]]
            lead_minutes = (episode_time - first_cross_time) / np.timedelta64(1, "m")
            lead_times.append(float(lead_minutes))

    n_caught = len(lead_times)
    n_episodes = n_caught + n_missed
    lead_arr = np.array(lead_times) if lead_times else np.array([0.0])

    return LeadTimeResult(
        n_episodes=n_episodes,
        n_caught=n_caught,
        n_missed=n_missed,
        mean_lead_time_minutes=round(float(lead_arr.mean()), 1) if n_caught else 0.0,
        median_lead_time_minutes=round(float(np.median(lead_arr)), 1) if n_caught else 0.0,
        pct_caught_30m_plus=round(float((lead_arr >= 30).mean() * 100), 1) if n_caught else 0.0,
        pct_caught_60m_plus=round(float((lead_arr >= 60).mean() * 100), 1) if n_caught else 0.0,
        lead_time_samples_minutes=[round(x, 1) for x in lead_times[:500]],
    )
