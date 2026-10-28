"""
Pytest Fixtures & Shared Test Environment.
"""

from __future__ import annotations

import os
import sys
import types
import uuid as _stdlib_uuid

# Ensure uuid_utils fallback if compiled extension is blocked by OS Application Control
if "uuid_utils" not in sys.modules:
    try:
        import uuid_utils
    except ImportError:
        mod = types.ModuleType("uuid_utils")
        mod.UUID = _stdlib_uuid.UUID
        mod.uuid1 = _stdlib_uuid.uuid1
        mod.uuid3 = _stdlib_uuid.uuid3
        mod.uuid4 = _stdlib_uuid.uuid4
        mod.uuid5 = _stdlib_uuid.uuid5
        mod.uuid6 = getattr(_stdlib_uuid, "uuid6", _stdlib_uuid.uuid1)
        mod.uuid7 = getattr(_stdlib_uuid, "uuid7", _stdlib_uuid.uuid4)
        mod.uuid8 = getattr(_stdlib_uuid, "uuid8", _stdlib_uuid.uuid4)
        mod._uuid4_int = lambda: _stdlib_uuid.uuid4().int
        mod._uuid7_int = lambda timestamp=None, nanos=None: getattr(_stdlib_uuid, "uuid7", _stdlib_uuid.uuid4)().int
        mod.SafeUUID = _stdlib_uuid.SafeUUID
        mod.getnode = _stdlib_uuid.getnode
        mod.NIL = _stdlib_uuid.UUID("00000000-0000-0000-0000-000000000000")
        mod.MAX = _stdlib_uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        mod.NAMESPACE_DNS = _stdlib_uuid.NAMESPACE_DNS
        mod.NAMESPACE_OID = _stdlib_uuid.NAMESPACE_OID
        mod.NAMESPACE_URL = _stdlib_uuid.NAMESPACE_URL
        mod.NAMESPACE_X500 = _stdlib_uuid.NAMESPACE_X500
        mod.RESERVED_FUTURE = _stdlib_uuid.RESERVED_FUTURE
        mod.RESERVED_MICROSOFT = _stdlib_uuid.RESERVED_MICROSOFT
        mod.RESERVED_NCS = _stdlib_uuid.RESERVED_NCS
        mod.RFC_4122 = _stdlib_uuid.RFC_4122
        mod.__version__ = "0.10.0"
        mod.reseed_rng = lambda: None
        sys.modules["uuid_utils"] = mod

        compat_mod = types.ModuleType("uuid_utils.compat")
        compat_mod.uuid7 = mod.uuid7
        compat_mod.uuid4 = mod.uuid4
        compat_mod.uuid1 = mod.uuid1
        compat_mod.uuid3 = mod.uuid3
        compat_mod.uuid5 = mod.uuid5
        compat_mod.uuid6 = mod.uuid6
        compat_mod.uuid8 = mod.uuid8
        compat_mod.UUID = mod.UUID
        sys.modules["uuid_utils.compat"] = compat_mod

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
