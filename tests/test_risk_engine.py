"""
Unit Tests: Deterministic Risk Engine.
Verifies every single rejection barrier and confirms orders are blocked before broker dispatch.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
import pytest

from src.risk_engine.engine import RiskEngine
from src.risk_engine.rules import RiskRuleViolation
from src.schemas.market import MarketSnapshot, NewsEvent
from src.schemas.system import CircuitBreakerStatus
from src.schemas.trade import OrderIntent, OrderSide


@pytest.fixture
def base_intent() -> OrderIntent:
    return OrderIntent(
        intent_id=f"intent_{uuid.uuid4().hex[:8]}",
        strategy_id="strat_test",
        version_id="v1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        requested_lots=0.10,
        stop_loss_price=1.0830,
        take_profit_price=1.0890,
        idempotency_key=f"idemp_{uuid.uuid4().hex[:8]}",
    )


def test_kill_switch_blocks_orders(base_intent, sample_snapshot):
    risk = RiskEngine()
    risk.trigger_kill_switch("Test emergency kill")
    res = risk.check(base_intent, {"equity": 100000.0}, sample_snapshot, [])
    assert res.approved is False
    assert res.violation == RiskRuleViolation.KILL_SWITCH_ENGAGED


def test_circuit_breaker_halted_blocks_orders(base_intent, sample_snapshot):
    risk = RiskEngine()
    risk.circuit_status = CircuitBreakerStatus.HALTED
    res = risk.check(base_intent, {"equity": 100000.0}, sample_snapshot, [])
    assert res.approved is False
    assert res.violation == RiskRuleViolation.CIRCUIT_BREAKER_HALTED


def test_daily_loss_limit_exceeded(base_intent, sample_snapshot):
    risk = RiskEngine()
    # Starting equity 100k, current 96k (4% loss, exceeds 3% max)
    account = {"starting_daily_equity": 100000.0, "equity": 96000.0}
    res = risk.check(base_intent, account, sample_snapshot, [])
    assert res.approved is False
    assert res.violation == RiskRuleViolation.DAILY_LOSS_LIMIT_EXCEEDED
    assert risk.circuit_status == CircuitBreakerStatus.PAUSED


def test_peak_drawdown_exceeded(base_intent, sample_snapshot):
    risk = RiskEngine()
    # Peak equity 120k, current 105k (12.5% peak drawdown exceeds 10% max, daily loss is 0%)
    account = {"starting_daily_equity": 105000.0, "peak_equity": 120000.0, "equity": 105000.0}
    res = risk.check(base_intent, account, sample_snapshot, [])
    assert res.approved is False
    assert res.violation == RiskRuleViolation.PEAK_DRAWDOWN_EXCEEDED
    assert risk.circuit_status == CircuitBreakerStatus.HALTED


def test_high_spread_rejection(base_intent, sample_snapshot):
    risk = RiskEngine()
    snap = sample_snapshot.model_copy(deep=True)
    snap.spread = 0.00035  # 3.5 pips > 2.5 max
    res = risk.check(base_intent, {"equity": 100000.0}, snap, [])
    assert res.approved is False
    assert res.violation == RiskRuleViolation.SPREAD_TOO_HIGH


def test_news_blackout_rejection(base_intent, sample_snapshot):
    risk = RiskEngine()
    snap = sample_snapshot.model_copy(deep=True)
    snap.news_events = [
        NewsEvent(
            time_utc=datetime.now(timezone.utc) + timedelta(minutes=15),
            currency="USD",
            impact="HIGH",
            title="Non-Farm Payrolls",
            minutes_until=15.0,
        )
    ]
    res = risk.check(base_intent, {"equity": 100000.0}, snap, [])
    assert res.approved is False
    assert res.violation == RiskRuleViolation.NEWS_BLACKOUT


def test_disallowed_session_rejection(base_intent, sample_snapshot):
    risk = RiskEngine()
    snap = sample_snapshot.model_copy(deep=True)
    snap.indicators.session = "ASIAN"  # Asian is not in default allowed [LONDON, NEW_YORK]
    res = risk.check(base_intent, {"equity": 100000.0}, snap, [])
    assert res.approved is False
    assert res.violation == RiskRuleViolation.DISALLOWED_SESSION


def test_duplicate_idempotency_key_rejection(base_intent, sample_snapshot):
    risk = RiskEngine()
    # First check passes
    res1 = risk.check(base_intent, {"equity": 100000.0}, sample_snapshot, [])
    assert res1.approved is True

    # Second check with identical idempotency key must be rejected
    res2 = risk.check(base_intent, {"equity": 100000.0}, sample_snapshot, [])
    assert res2.approved is False
    assert res2.violation == RiskRuleViolation.DUPLICATE_IDEMPOTENCY_KEY


def test_all_barriers_pass_and_sizes_lots(base_intent, sample_snapshot):
    risk = RiskEngine()
    res = risk.check(base_intent, {"equity": 100000.0, "free_margin": 95000.0}, sample_snapshot, [])
    assert res.approved is True
    assert res.approved_lots > 0.0
    # Sizing respects 5% max position equity limit
    assert res.approved_lots <= 0.05


def test_max_position_equity_pct_enforced():
    from src.risk_engine.sizing import calculate_risk_sized_lots
    # Account equity = $100,000, max_position_equity_pct = 0.05 (Max notional = $5,000)
    # EURUSD price = 1.0860, point_value = 100,000
    # Stop distance is very small (0.0004 -> 4 pips), raw stop risk would size to 25 lots!
    # But notional exposure cap restricts it: 5000 / (1.0860 * 100000) = 0.046 -> 0.04 lots
    lots = calculate_risk_sized_lots(
        equity=100000.0,
        stop_distance_price=0.0004,
        risk_fraction=0.01,
        current_price=1.0860,
        max_position_equity_pct=0.05,
    )
    assert lots == 0.04
