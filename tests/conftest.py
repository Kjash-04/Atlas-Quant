"""
Pytest Fixtures & Shared Test Environment.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add root directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.connection import Base
from src.schemas.market import MarketSnapshot, IndicatorSet, RegimeLabel
from src.schemas.strategy import StrategySpec, Rule, RuleLogic, PositionSizingSpec, RiskControlsSpec


@pytest.fixture(scope="session")
def test_db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="function")
def db_session(test_db_engine):
    connection = test_db_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_market_df() -> pd.DataFrame:
    np.random.seed(42)
    bars = 300
    dates = pd.date_range("2026-06-01", periods=bars, freq="15min", tz="UTC")
    price = 1.0850 + np.cumsum(np.random.normal(0.00005, 0.0003, bars))
    df = pd.DataFrame({
        "timestamp_utc": dates,
        "open": price,
        "high": price + 0.0006,
        "low": price - 0.0006,
        "close": price + 0.0001,
        "volume": 500.0,
        "spread": 0.00015,
    })
    return df


@pytest.fixture
def sample_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="EURUSD",
        timestamp_utc=datetime.now(timezone.utc),
        timeframe="M15",
        open=1.0850,
        high=1.0865,
        low=1.0845,
        close=1.0860,
        volume=1200.0,
        spread=0.00015,
        indicators=IndicatorSet(
            ema_20=1.0855,
            ema_50=1.0840,
            rsi_14=58.5,
            atr_14=0.0014,
            atr_percentile_100=55.0,
            session="LONDON",
        ),
        regime_label=RegimeLabel.TRENDING_BULL,
    )


@pytest.fixture
def sample_strategy_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="strat_test_spec",
        version="v1.0.0",
        hypothesis_id="hyp-test-01",
        status="CODED",
        universe=["EURUSD"],
        timeframe="M15",
        entry_logic=RuleLogic.AND,
        entry_rules=[
            Rule(feature="ema_20", operator="CROSS_ABOVE", value="ema_50", lookback=1),
            Rule(feature="rsi_14", operator="<", value=70.0, lookback=1),
        ],
        exit_logic=RuleLogic.OR,
        exit_rules=[
            Rule(feature="ema_20", operator="CROSS_BELOW", value="ema_50", lookback=1),
        ],
        stop_loss_atr_mult=1.5,
        take_profit_rr=2.0,
        position_sizing=PositionSizingSpec(risk_per_trade=0.01),
        risk_controls=RiskControlsSpec(
            max_daily_trades=10,
            news_blackout_minutes=30,
            max_spread_pips=2.5,
            allowed_sessions=["LONDON", "NEW_YORK"],
            max_open_positions=3,
        ),
        parameter_ranges={"ema_fast": [15, 20, 25], "rsi_period": [10, 14, 18]},
    )
