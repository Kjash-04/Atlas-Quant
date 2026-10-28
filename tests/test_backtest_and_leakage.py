"""
Unit Tests: Backtesting Engine, Chronological Splits, and Signal Causality.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine
from src.schemas.strategy import StrategySpec
from src.strategies.generated.ema_rsi_trend import EmaRsiTrendStrategy


def test_chronological_splits(sample_market_df):
    engine = BacktestEngine(is_ratio=0.60, oos_ratio=0.20, test_ratio=0.20, embargo_bars=10)
    is_df, oos_df, test_df = engine.split_data(sample_market_df)

    # Verify no overlapping indices
    is_indices = set(is_df.index)
    oos_indices = set(oos_df.index)
    test_indices = set(test_df.index)

    assert len(is_indices.intersection(oos_indices)) == 0
    assert len(oos_indices.intersection(test_indices)) == 0

    # Verify chronological order
    assert is_df["timestamp_utc"].max() < oos_df["timestamp_utc"].min()
    assert oos_df["timestamp_utc"].max() < test_df["timestamp_utc"].min()


def test_backtest_simulation_with_friction_costs(sample_strategy_spec, sample_market_df, db_session):
    strategy = EmaRsiTrendStrategy(sample_strategy_spec)
    engine = BacktestEngine()

    result = engine.run_validation_pipeline(strategy, sample_market_df, db=db_session, evaluate_test_set=True)
    assert result.run_id.startswith("bt_")
    assert result.is_metrics is not None
    assert result.oos_metrics is not None
    assert result.costs_breakdown["total_friction_usd"] >= 0.0
