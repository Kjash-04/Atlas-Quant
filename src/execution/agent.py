"""
Execution Agent.
Coordinates pre-trade RiskEngine gating, adapter dispatch, and post-trade lifecycle persistence.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from src.config import settings
from src.database.connection import SessionLocal
from src.database.models import TradeModel
from src.execution.base import BaseExecutionAdapter
from src.execution.mt5_adapter import MT5ExecutionAdapter
from src.execution.paper_adapter import PaperAdapter
from src.risk_engine.engine import RiskEngine, risk_engine
from src.schemas.market import MarketSnapshot
from src.schemas.trade import OrderExecutionResult, OrderIntent

logger = logging.getLogger(__name__)


class ExecutionAgent:
    def __init__(
        self,
        risk: Optional[RiskEngine] = None,
        adapter: Optional[BaseExecutionAdapter] = None,
    ):
        self.risk = risk or risk_engine
        if adapter is not None:
            self.adapter = adapter
        else:
            if settings.PAPER_TRADING:
                self.adapter = PaperAdapter()
            else:
                self.adapter = MT5ExecutionAdapter()
        self.adapter.connect()

    def update_broker_heartbeat(self) -> None:
        """Explicit broker heartbeat ping, decoupling health monitoring from order gating."""
        if self.adapter.is_connected:
            self.risk.update_broker_heartbeat()

    def process_order_intent(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
        db: Optional[Session] = None,
    ) -> OrderExecutionResult:
        """
        Executes order strictly gated by RiskEngine.
        If RiskEngine rejects, NEVER passes order to broker.
        """
        # 0. Direct connectivity gate
        if not self.adapter.is_connected:
            logger.warning(f"ExecutionAgent: Broker adapter disconnected. OrderIntent {intent.intent_id} blocked.")
            return OrderExecutionResult(
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                side=intent.side,
                executed_lots=0.0,
                executed_price=0.0,
                spread_paid_pips=0.0,
                slippage_pips=0.0,
                commission_usd=0.0,
                status="REJECTED",
                error_message="Broker connection offline",
            )

        recent_trades = recent_trades or []
        account_info = self.adapter.get_account_info()

        # 1. Evaluate RiskEngine Gate (independent broker heartbeat check)
        risk_result = self.risk.check(
            intent=intent,
            account_info=account_info,
            snapshot=snapshot,
            recent_trades=recent_trades,
            db=db,
        )

        if not risk_result.approved:
            logger.warning(f"RiskEngine REJECTED OrderIntent {intent.intent_id}: {risk_result.reason}")
            return OrderExecutionResult(
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                side=intent.side,
                executed_lots=0.0,
                executed_price=0.0,
                spread_paid_pips=0.0,
                slippage_pips=0.0,
                commission_usd=0.0,
                status="REJECTED",
                error_message=f"RiskGate Rejection: {risk_result.reason}",
            )

        # 2. Risk Passed -> Dispatch to Execution Adapter with live snapshot
        logger.info(f"RiskEngine APPROVED OrderIntent {intent.intent_id} for {risk_result.approved_lots} lots.")
        exec_result = self.adapter.send_order(
            intent, approved_lots=risk_result.approved_lots, snapshot=snapshot
        )

        # 3. Persist Trade Record if Filled
        if exec_result.status == "FILLED":
            self._persist_trade_record(intent, exec_result, db)

        return exec_result

    def _persist_trade_record(
        self,
        intent: OrderIntent,
        exec_res: OrderExecutionResult,
        db: Optional[Session] = None,
    ) -> None:
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            trade_id = f"tr_{uuid.uuid4().hex[:8]}"
            trade = TradeModel(
                trade_id=trade_id,
                broker_ticket=exec_res.broker_ticket,
                strategy_id=intent.strategy_id,
                version_id=intent.version_id,
                symbol=intent.symbol,
                side=intent.side.value,
                entry_time=exec_res.executed_at,
                entry_price=exec_res.executed_price,
                lots=exec_res.executed_lots,
                commission_usd=exec_res.commission_usd,
                is_paper=settings.PAPER_TRADING,
            )
            db.add(trade)
            db.commit()
            logger.info(f"Trade {trade_id} persisted to database.")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist trade record: {e}")
        finally:
            if own_session:
                db.close()

    def emergency_flatten_and_kill(self, reason: str = "Admin Emergency Kill") -> int:
        """Triggered on emergency kill switch or severe risk limit breach."""
        self.risk.trigger_kill_switch(reason=reason)
        closed_count = self.adapter.flatten_all_positions()
        logger.critical(f"ExecutionAgent: Flattened {closed_count} positions and engaged kill switch.")
        return closed_count


execution_agent = ExecutionAgent()
