"""
Integration Tests: ExecutionAgent & Broker Adapters.
Proves that risk rejections prevent any order from reaching execution adapters.
"""

from __future__ import annotations

import uuid
import pytest

from src.execution.agent import ExecutionAgent
from src.execution.paper_adapter import PaperAdapter
from src.risk_engine.engine import RiskEngine
from src.schemas.trade import OrderIntent, OrderSide


def test_execution_agent_blocks_rejected_order(sample_snapshot, db_session):
    risk = RiskEngine()
    risk.trigger_kill_switch("Test kill switch")
    paper = PaperAdapter()
    agent = ExecutionAgent(risk=risk, adapter=paper)

    intent = OrderIntent(
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

    result = agent.process_order_intent(intent, snapshot=sample_snapshot, db=db_session)
    assert result.status == "REJECTED"
    assert "RiskGate Rejection" in result.error_message
    assert len(paper.get_open_positions()) == 0


def test_execution_agent_executes_approved_order(sample_snapshot, db_session):
    risk = RiskEngine()
    paper = PaperAdapter()
    agent = ExecutionAgent(risk=risk, adapter=paper)

    intent = OrderIntent(
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

    result = agent.process_order_intent(intent, snapshot=sample_snapshot, db=db_session)
    assert result.status == "FILLED"
    assert result.broker_ticket is not None
    assert len(paper.get_open_positions()) == 1


def test_emergency_flatten_and_kill(sample_snapshot, db_session):
    risk = RiskEngine()
    paper = PaperAdapter()
    agent = ExecutionAgent(risk=risk, adapter=paper)

    intent = OrderIntent(
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
    agent.process_order_intent(intent, snapshot=sample_snapshot, db=db_session)
    assert len(paper.get_open_positions()) == 1

    # Emergency kill
    closed = agent.emergency_flatten_and_kill("Test emergency")
    assert closed == 1
    assert len(paper.get_open_positions()) == 0
    assert risk.kill_switch_engaged is True
