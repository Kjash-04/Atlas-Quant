"""
Paper Trading Execution Adapter.
Simulates realistic broker fills with spread, slippage, and position lifecycle management.
Zero real capital risk.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from src.execution.base import BaseExecutionAdapter
from src.schemas.market import MarketSnapshot
from src.schemas.trade import OrderExecutionResult, OrderIntent, OrderSide

logger = logging.getLogger(__name__)

SUPPORTED_SYMBOLS: set[str] = {
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"
}


class PaperAdapter(BaseExecutionAdapter):
    def __init__(self, initial_balance: float = 100000.0):
        self.balance = initial_balance
        self.equity = initial_balance
        self.starting_daily_equity = initial_balance
        self.peak_equity = initial_balance
        self.positions: Dict[int, Dict[str, Any]] = {}
        self.ticket_counter = 100000
        self.is_connected = True

    def connect(self) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        self.is_connected = False

    def send_order(
        self,
        intent: OrderIntent,
        approved_lots: float,
        snapshot: Optional[MarketSnapshot] = None,
    ) -> OrderExecutionResult:
        if not self.is_connected:
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
                error_message="PaperAdapter disconnected",
            )

        if intent.symbol.upper() not in SUPPORTED_SYMBOLS:
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
                error_message=f"PaperAdapter: Unsupported symbol '{intent.symbol}'",
            )

        self.ticket_counter += 1
        ticket = self.ticket_counter

        # Realistic spread and fill price simulation from live snapshot
        if snapshot is not None:
            base_price = snapshot.close
            spread_pips = round(snapshot.spread * 10000.0, 2)
        else:
            base_price = getattr(intent, "price", None) or (1.0850 if intent.symbol == "EURUSD" else 1.2550)
            spread_pips = 1.2

        slippage_pips = round(random.uniform(0.1, 0.6), 2)
        pip_val = 0.0001

        if intent.side == OrderSide.BUY:
            fill_price = base_price + (spread_pips / 2.0 + slippage_pips) * pip_val
        else:
            fill_price = base_price - (spread_pips / 2.0 + slippage_pips) * pip_val

        commission_usd = round(3.50 * approved_lots, 2)
        self.equity -= commission_usd

        # Store position
        self.positions[ticket] = {
            "ticket": ticket,
            "symbol": intent.symbol,
            "side": intent.side.value,
            "lots": approved_lots,
            "entry_price": fill_price,
            "stop_loss": intent.stop_loss_price,
            "take_profit": intent.take_profit_price,
            "open_time": datetime.now(timezone.utc),
        }

        logger.info(f"PaperAdapter: Filled order #{ticket} for {approved_lots} lots {intent.symbol} @ {fill_price:.5f}")

        return OrderExecutionResult(
            intent_id=intent.intent_id,
            broker_ticket=ticket,
            symbol=intent.symbol,
            side=intent.side,
            executed_lots=approved_lots,
            executed_price=round(fill_price, 5),
            spread_paid_pips=spread_pips,
            slippage_pips=slippage_pips,
            commission_usd=commission_usd,
            status="FILLED",
            error_message=None,
        )

    def cancel_order(self, ticket: int) -> bool:
        if ticket in self.positions:
            del self.positions[ticket]
            return True
        return False

    def get_account_info(self) -> Dict[str, Any]:
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "starting_daily_equity": round(self.starting_daily_equity, 2),
            "peak_equity": round(self.peak_equity, 2),
            "free_margin": round(self.equity * 0.95, 2),
            "open_positions_count": len(self.positions),
        }

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return list(self.positions.values())

    def flatten_all_positions(self) -> int:
        count = len(self.positions)
        self.positions.clear()
        logger.info(f"PaperAdapter: Flattened {count} open positions.")
        return count
