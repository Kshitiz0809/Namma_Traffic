"""
Phase 6 Task 4 test: demo_seed.py runs end-to-end against real data with
frozen models, no retraining. Marked slow (loads parquet + 2 CatBoost models).
"""

import pytest

from app.models.demo_seed import (
    ESCALATION_EXAMPLE_CELL,
    ESCALATION_EXAMPLE_TIMESTAMP,
    HOTSPOT_GROWTH_CELL,
    HOTSPOT_GROWTH_DATE,
    DemoContext,
    replay_alerts,
    showcase_recommendations,
    simulate_hotspot_growth,
)


@pytest.fixture(scope="module")
def ctx():
    return DemoContext()


@pytest.mark.slow
def test_replay_alerts_runs_without_error(ctx, capsys):
    replay_alerts(ctx, fast=True, n=3)
    out = capsys.readouterr().out
    assert "DEMO 1" in out
    assert "Monitor" in out or "Patrol" in out or "Deploy" in out or "Tow" in out


@pytest.mark.slow
def test_hotspot_growth_scenario_cell_exists_in_data(ctx):
    sub = ctx.features[ctx.features["h3_cell"] == HOTSPOT_GROWTH_CELL]
    sub = sub[sub["created_datetime"].dt.date.astype(str) == HOTSPOT_GROWTH_DATE]
    assert len(sub) > 0, "Hotspot growth demo cell/date must exist in the real dataset"


@pytest.mark.slow
def test_simulate_hotspot_growth_runs_without_error(ctx, capsys):
    simulate_hotspot_growth(ctx, fast=True)
    out = capsys.readouterr().out
    assert "DEMO 2" in out
    assert "risk=" in out


@pytest.mark.slow
def test_escalation_example_exists_and_is_real(ctx):
    import pandas as pd

    rows = ctx.features[
        (ctx.features["h3_cell"] == ESCALATION_EXAMPLE_CELL)
        & (ctx.features["vehicle_type"] == "MAXI-CAB")
        & (ctx.features["created_datetime"] == pd.Timestamp(ESCALATION_EXAMPLE_TIMESTAMP, tz="UTC"))
    ]
    # >=1, not ==1: this exact (cell, vehicle_type, timestamp) combination
    # happens to have 2 real rows -- consistent with the duplicate-vehicle-
    # event data quirk documented in Phase 2/3 (ADR-007), not a test bug.
    assert len(rows) >= 1, "Escalation demo example must match at least one real row"


@pytest.mark.slow
def test_showcase_recommendations_escalates_the_real_example(ctx, capsys):
    showcase_recommendations(ctx, fast=True)
    out = capsys.readouterr().out
    assert "DEMO 3" in out
    assert "Tow operation candidate" in out
    assert "escalated=True" in out
    assert "Cold start" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
