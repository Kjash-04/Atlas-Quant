"""
Regression tests for Atlas-Quant Deep Audit Fixes (Bugs 1 - 9).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import settings
from src.database.connection import SessionLocal, init_db
from src.database.models import (
    BacktestRunModel,
    MarketSnapshotModel,
    StrategyVersionModel,
    TradeModel,
)
from src.execution.agent import ExecutionAgent
from src.execution.paper_adapter import PaperAdapter
from src.risk_engine.engine import RiskEngine
from src.risk_engine.rules import RiskRuleViolation
from src.schemas.backtest import BacktestMetrics, BacktestRunResult
from src.schemas.market import MarketSnapshot, IndicatorSet, RegimeLabel
from src.schemas.strategy import StrategySpec, Rule, RuleLogic, PositionSizingSpec, RiskControlsSpec
from src.schemas.trade import OrderIntent, OrderSide
from src.self_improvement.orchestrator import SelfImprovementOrchestrator
from src.self_improvement.states import SelfImprovementState
from src.strategies.generated.ema_rsi_trend import EmaRsiTrendStrategy


# ---------------------------------------------------------------------------
# BUG 1: Truthful metrics and REVERT on zero/failing Sharpe
# ---------------------------------------------------------------------------
def test_bug1_no_metric_fabrication_and_enforces_revert(sample_market_df):
    """Zero Sharpe must not evaluate to 1.65, and failing criteria must REVERT."""
    orchestrator = SelfImprovementOrchestrator(data_df=sample_market_df)

    # Mock backtester returning 0.0 metrics
    class ZeroBacktester:
        def run_validation_pipeline(self, strategy, df, **kwargs):
            zero_m = BacktestMetrics(
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                expectancy_usd=0.0,
                profit_factor=0.0,
                win_rate_pct=0.0,
                total_trades=0,
            )
            return BacktestRunResult(
                run_id="bt_zero",
                strategy_id=strategy.strategy_id,
                version_id=strategy.version,
                data_hash="hash",
                code_hash="hash",
                param_hash="hash",
                is_metrics=zero_m,
                oos_metrics=zero_m,
                passes_champion_criteria=False,
                rejection_reasons=["Zero trades"],
            )

    orchestrator.backtester = ZeroBacktester()

    state = SelfImprovementState(
        cycle_id="cycle_test_zero",
        strategy_id="strat_test",
        champion_metrics={"sharpe_ratio": 1.15, "max_drawdown_pct": 11.8, "expectancy_usd": 40.0},
    )

    validate_out = orchestrator.validate_node(state)

    # Verify metrics are NOT fabricated
    assert validate_out["challenger_metrics"]["sharpe_ratio"] == 0.0
    assert validate_out["challenger_metrics"]["expectancy_usd"] == 0.0
    assert validate_out["challenger_metrics"]["max_drawdown_pct"] == 0.0
    assert validate_out["validation_passed"] is False

    # Check keep or revert node
    state.update(validate_out)
    decision_out = orchestrator.keep_or_revert_node(state)
    assert decision_out["decision"] == "REVERT"


# ---------------------------------------------------------------------------
# BUG 2: Dynamic StrategySpec evaluation in EmaRsiTrendStrategy
# ---------------------------------------------------------------------------
def test_bug2_different_specs_produce_different_signals(sample_market_df):
    """Different entry rules in StrategySpec must produce different signals."""
    spec_a = StrategySpec(
        strategy_id="strat_test",
        hypothesis_id="hyp-a",
        entry_rules=[
            Rule(feature="rsi_14", operator="<", value=40.0),
        ],
        exit_rules=[
            Rule(feature="rsi_14", operator=">", value=60.0),
        ],
    )

    spec_b = StrategySpec(
        strategy_id="strat_test",
        hypothesis_id="hyp-b",
        entry_rules=[
            Rule(feature="close", operator=">", value=1.0855),
        ],
        exit_rules=[
            Rule(feature="close", operator="<", value=1.0845),
        ],
    )

    strat_a = EmaRsiTrendStrategy(spec_a)
    strat_b = EmaRsiTrendStrategy(spec_b)

    sig_a = strat_a.generate_signals(sample_market_df)
    sig_b = strat_b.generate_signals(sample_market_df)

    # Ensure both generated signals and they differ based on rules
    assert not sig_a.equals(sig_b)


# ---------------------------------------------------------------------------
# BUG 3: Champion metrics queried from database
# ---------------------------------------------------------------------------
def test_bug3_champion_metrics_queried_from_db(db_session, sample_market_df):
    """Champion metrics should be resolved from BacktestRunModel in database."""
    strat_id = f"strat_champ_{uuid.uuid4().hex[:6]}"
    champ_ver_id = f"{strat_id}_v1.0.0"

    # Seed champion version
    champ_ver = StrategyVersionModel(
        version_id=champ_ver_id,
        strategy_id=strat_id,
        hypothesis_id="hyp-01",
        spec_json={},
        python_code="# code",
        code_hash="c_hash",
        param_hash="p_hash",
        status="CHAMPION",
    )
    db_session.add(champ_ver)

    # Seed backtest run with custom metrics
    bt_run = BacktestRunModel(
        run_id=f"bt_{uuid.uuid4().hex[:6]}",
        strategy_id=strat_id,
        version_id=champ_ver_id,
        data_hash="d_hash",
        code_hash="c_hash",
        param_hash="p_hash",
        is_metrics={"sharpe_ratio": 2.20, "max_drawdown_pct": 5.0, "expectancy_usd": 70.0},
        oos_metrics={"sharpe_ratio": 2.10, "max_drawdown_pct": 6.5, "expectancy_usd": 65.0},
        passes_champion_criteria=True,
    )
    db_session.add(bt_run)
    db_session.commit()

    orchestrator = SelfImprovementOrchestrator(data_df=sample_market_df, db=db_session)
    state = SelfImprovementState(
        cycle_id="cycle_champ_test",
        strategy_id=strat_id,
        challenger_spec_json={"strategy_id": strat_id, "hypothesis_id": "hyp-02", "entry_rules": [], "exit_rules": []},
    )

    out = orchestrator.validate_node(state)
    assert out["champion_metrics"]["sharpe_ratio"] == 2.10
    assert out["champion_metrics"]["max_drawdown_pct"] == 6.5
    assert out["champion_metrics"]["expectancy_usd"] == 65.0


# ---------------------------------------------------------------------------
# BUG 4: observe_node queries TradeModel and MarketSnapshotModel from DB
# ---------------------------------------------------------------------------
def test_bug4_observe_node_queries_db_records(db_session, monkeypatch):
    strat_id = f"strat_obs_{uuid.uuid4().hex[:6]}"

    # Add historical trade
    trade = TradeModel(
        trade_id=f"tr_{uuid.uuid4().hex[:6]}",
        strategy_id=strat_id,
        version_id=f"{strat_id}_v1",
        symbol="EURUSD",
        side="BUY",
        entry_time=datetime.now(timezone.utc),
        entry_price=1.0850,
        lots=0.10,
        pnl_usd=-35.0,
    )
    db_session.add(trade)

    # Add snapshot
    snap = MarketSnapshotModel(
        symbol="EURUSD",
        timestamp_utc=datetime.now(timezone.utc),
        timeframe="M15",
        open=1.0850,
        high=1.0860,
        low=1.0840,
        close=1.0855,
        volume=600.0,
        spread=0.00015,
        regime_label="RANGING_HIGH_VOL",
        data_hash="dh_test",
    )
    db_session.add(snap)
    db_session.commit()

    captured = {}
    def mock_observe_residuals(strategy_id, trade_logs, market_context, **kwargs):
        captured["strategy_id"] = strategy_id
        captured["trade_logs"] = trade_logs
        captured["market_context"] = market_context
        return {
            "observation": "Losses cluster during high vol",
            "loss_concentration_pct": 75.0,
            "affected_regime": "RANGING_HIGH_VOL",
        }

    orchestrator = SelfImprovementOrchestrator(db=db_session)
    monkeypatch.setattr(orchestrator.critic, "observe_residuals", mock_observe_residuals)

    state = SelfImprovementState(cycle_id="cycle_obs_test", strategy_id=strat_id)
    out = orchestrator.observe_node(state)

    assert "observed_residuals" in out
    assert len(captured["trade_logs"]) == 1
    assert captured["trade_logs"][0]["trade_id"] == trade.trade_id
    assert captured["trade_logs"][0]["pnl"] == -35.0
    assert captured["market_context"]["active_regime"] == "RANGING_HIGH_VOL"
    assert captured["market_context"]["symbol"] == "EURUSD"
    assert len(out.get("audit_events", [])) >= 1


# ---------------------------------------------------------------------------
# BUG 5: requested_lots validation and sizing capping
# ---------------------------------------------------------------------------
def test_bug5_requested_lots_bounds_and_capping(sample_snapshot):
    risk = RiskEngine()
    account = {"starting_daily_equity": 100000.0, "equity": 100000.0, "peak_equity": 100000.0}

    # Zero lots -> rejected
    zero_intent = OrderIntent(
        intent_id="int_0",
        strategy_id="strat_test",
        version_id="v1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        requested_lots=0.0,
        stop_loss_price=1.0830,
        take_profit_price=1.0890,
        idempotency_key="idemp_0",
    )
    res_zero = risk.check(zero_intent, account, sample_snapshot, [])
    assert not res_zero.approved
    assert res_zero.violation == RiskRuleViolation.LOT_SIZE_OUT_OF_BOUNDS

    # Negative lots -> rejected
    neg_intent = OrderIntent(
        intent_id="int_neg",
        strategy_id="strat_test",
        version_id="v1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        requested_lots=-0.5,
        stop_loss_price=1.0830,
        take_profit_price=1.0890,
        idempotency_key="idemp_neg",
    )
    res_neg = risk.check(neg_intent, account, sample_snapshot, [])
    assert not res_neg.approved
    assert res_neg.violation == RiskRuleViolation.LOT_SIZE_OUT_OF_BOUNDS

    # Requested lots small (0.02) when max risk allows e.g. > 0.5 -> approved_lots must be capped to 0.02
    small_intent = OrderIntent(
        intent_id="int_small",
        strategy_id="strat_test",
        version_id="v1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        requested_lots=0.02,
        stop_loss_price=1.0830,
        take_profit_price=1.0890,
        idempotency_key="idemp_small",
    )
    res_small = risk.check(small_intent, account, sample_snapshot, [])
    assert res_small.approved
    assert res_small.approved_lots == 0.02


# ---------------------------------------------------------------------------
# BUG 6: Stop-Loss / Take-Profit bracket sanity checks
# ---------------------------------------------------------------------------
def test_bug6_bracket_price_sanity(sample_snapshot):
    risk = RiskEngine()
    account = {"starting_daily_equity": 100000.0, "equity": 100000.0, "peak_equity": 100000.0}
    # Market close is 1.0860

    # Inverted BUY: SL above market
    buy_sl_above = OrderIntent(
        intent_id="buy_bad_sl",
        strategy_id="strat_test",
        version_id="v1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        requested_lots=0.1,
        stop_loss_price=1.0900,  # > 1.0860
        take_profit_price=1.0950,
        idempotency_key="idemp_buy_bad_sl",
    )
    res = risk.check(buy_sl_above, account, sample_snapshot, [])
    assert not res.approved
    assert res.violation == RiskRuleViolation.INVALID_BRACKET_PRICES

    # Inverted BUY: TP below market
    buy_tp_below = OrderIntent(
        intent_id="buy_bad_tp",
        strategy_id="strat_test",
        version_id="v1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        requested_lots=0.1,
        stop_loss_price=1.0800,
        take_profit_price=1.0850,  # < 1.0860
        idempotency_key="idemp_buy_bad_tp",
    )
    res = risk.check(buy_tp_below, account, sample_snapshot, [])
    assert not res.approved
    assert res.violation == RiskRuleViolation.INVALID_BRACKET_PRICES

    # Inverted SELL: SL below market
    sell_sl_below = OrderIntent(
        intent_id="sell_bad_sl",
        strategy_id="strat_test",
        version_id="v1.0.0",
        symbol="EURUSD",
        side=OrderSide.SELL,
        requested_lots=0.1,
        stop_loss_price=1.0800,  # < 1.0860
        take_profit_price=1.0750,
        idempotency_key="idemp_sell_bad_sl",
    )
    res = risk.check(sell_sl_below, account, sample_snapshot, [])
    assert not res.approved
    assert res.violation == RiskRuleViolation.INVALID_BRACKET_PRICES

    # Inverted SELL: TP above market
    sell_tp_above = OrderIntent(
        intent_id="sell_bad_tp",
        strategy_id="strat_test",
        version_id="v1.0.0",
        symbol="EURUSD",
        side=OrderSide.SELL,
        requested_lots=0.1,
        stop_loss_price=1.0900,
        take_profit_price=1.0880,  # > 1.0860
        idempotency_key="idemp_sell_bad_tp",
    )
    res = risk.check(sell_tp_above, account, sample_snapshot, [])
    assert not res.approved
    assert res.violation == RiskRuleViolation.INVALID_BRACKET_PRICES


# ---------------------------------------------------------------------------
# BUG 7: Symbol whitelist check in RiskEngine & PaperAdapter
# ---------------------------------------------------------------------------
def test_bug7_symbol_whitelist(sample_snapshot):
    risk = RiskEngine()
    account = {"starting_daily_equity": 100000.0, "equity": 100000.0, "peak_equity": 100000.0}

    unsupported_intent = OrderIntent(
        intent_id="bad_sym",
        strategy_id="strat_test",
        version_id="v1.0.0",
        symbol="UNSUPPORTED_COIN",
        side=OrderSide.BUY,
        requested_lots=0.1,
        stop_loss_price=1.0800,
        take_profit_price=1.0900,
        idempotency_key="idemp_bad_sym",
    )
    res = risk.check(unsupported_intent, account, sample_snapshot, [])
    assert not res.approved
    assert res.violation == RiskRuleViolation.UNSUPPORTED_SYMBOL

    # Test PaperAdapter whitelist enforcement
    adapter = PaperAdapter()
    adapter.connect()
    exec_res = adapter.send_order(unsupported_intent, approved_lots=0.1, snapshot=sample_snapshot)
    assert exec_res.status == "REJECTED"
    assert "Unsupported symbol" in (exec_res.error_message or "")


# ---------------------------------------------------------------------------
# BUG 8: API /orders returns 422 Unprocessable Entity on risk rejection
# ---------------------------------------------------------------------------
def test_bug8_api_orders_returns_422_on_risk_rejection():
    init_db()
    with TestClient(app) as client:
        headers = {"X-API-Key": settings.ADMIN_API_KEY}
        payload = {
            "intent_id": f"int_{uuid.uuid4().hex[:8]}",
            "strategy_id": "strat_test",
            "version_id": "v1.0.0",
            "symbol": "FAKEPAIR",  # will fail symbol whitelist
            "side": "BUY",
            "requested_lots": 0.10,
            "stop_loss_price": 1.0800,
            "take_profit_price": 1.0900,
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:8]}",
        }
        res = client.post("/orders", json=payload, headers=headers)
        assert res.status_code == 422
        body = res.json()
        assert "detail" in body
        assert body["detail"]["status"] == "REJECTED"


# ---------------------------------------------------------------------------
# BUG 9: ExecutionAgent binds active CHAMPION version at runtime
# ---------------------------------------------------------------------------
def test_bug9_execution_agent_wires_active_champion(db_session, sample_snapshot):
    agent = ExecutionAgent()

    strat_id = f"strat_champ_wire_{uuid.uuid4().hex[:6]}"
    active_champ_version = f"{strat_id}_v2.5.0"

    # Seed CHAMPION in DB
    champ_ver = StrategyVersionModel(
        version_id=active_champ_version,
        strategy_id=strat_id,
        hypothesis_id="hyp-09",
        spec_json={},
        python_code="# code",
        code_hash="c_hash",
        param_hash="p_hash",
        status="CHAMPION",
    )
    db_session.add(champ_ver)
    db_session.commit()

    resolved_version = agent.get_active_champion(strat_id, db=db_session)
    assert resolved_version == active_champ_version

    # Process intent with default version_id -> should be rebound to active champion
    intent = OrderIntent(
        intent_id=f"int_{uuid.uuid4().hex[:8]}",
        strategy_id=strat_id,
        version_id="default",
        symbol="EURUSD",
        side=OrderSide.BUY,
        requested_lots=0.1,
        stop_loss_price=1.0800,
        take_profit_price=1.0900,
        idempotency_key=f"idemp_{uuid.uuid4().hex[:8]}",
    )

    agent.process_order_intent(intent, snapshot=sample_snapshot, db=db_session)
    assert intent.version_id == active_champ_version
