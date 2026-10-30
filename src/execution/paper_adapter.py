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

        # Opening commission ($3.50 / lot)
        commission_usd = round(3.50 * approved_lots, 2)
        open_commission = commission_usd
        self.equity = round(self.equity - open_commission, 2)

        # Store position
        self.positions[ticket] = {
            "ticket": ticket,
            "symbol": intent.symbol,
            "side": intent.side.value,
            "lots": approved_lots,
            "entry_price": fill_price,
            "stop_loss": intent.stop_loss_price,
            "take_profit": intent.take_profit_price,
            "commission_usd": open_commission,
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

    def close_position(
        self,
        ticket: int,
        exit_price: float,
        exit_time: Optional[datetime] = None,
        exit_reason: str = "MANUAL",
    ) -> Optional[Dict[str, Any]]:
        """
        Closes an open position, realizes gross & net PnL (accounting for commission),
        and updates account equity and balance.
        """
        if ticket not in self.positions:
            return None

        pos = self.positions.pop(ticket)
        side = pos["side"]
        entry_price = pos["entry_price"]
        lots = pos["lots"]
        close_time = exit_time or datetime.now(timezone.utc)

        # Standard FX contract size = 100,000 units
        contract_size = 100000.0
        pip_factor = 10000.0

        if side in (OrderSide.BUY.value, "BUY"):
            price_diff = exit_price - entry_price
        else:
            price_diff = entry_price - exit_price

        gross_pnl = price_diff * lots * contract_size
        pnl_pips = round(price_diff * pip_factor, 1)

        # Closing commission ($3.50 / lot) and round-turn total commission
        open_commission = pos.get("commission_usd", 0.0)
        close_commission = round(3.50 * lots, 2)
        total_commission = round(open_commission + close_commission, 2)
        net_pnl = round(gross_pnl - total_commission, 2)

        # Realize PnL: balance credits full round-turn net PnL; equity credits gross minus closing commission
        self.balance = round(self.balance + net_pnl, 2)
        self.equity = round(self.equity + gross_pnl - close_commission, 2)
        self.peak_equity = max(self.peak_equity, self.equity)

        closed_data = {
            "ticket": ticket,
            "symbol": pos["symbol"],
            "side": side,
            "lots": lots,
            "entry_price": entry_price,
            "exit_price": round(exit_price, 5),
            "open_time": pos["open_time"],
            "exit_time": close_time,
            "pnl_usd": net_pnl,
            "pnl_pips": pnl_pips,
            "commission_usd": total_commission,
            "exit_reason": exit_reason,
        }
        logger.info(
            f"PaperAdapter: Closed #{ticket} {side} {lots} {pos['symbol']} @ {exit_price:.5f} | "
            f"PnL: ${net_pnl:+.2f} ({pnl_pips:+.1f} pips) | Reason: {exit_reason}"
        )
        return closed_data

    def tick_positions(self, snapshot: MarketSnapshot) -> List[Dict[str, Any]]:
        """
        Evaluates active open positions against incoming snapshot price bounds (high/low).
        Triggers automatic stop-loss or take-profit execution.
        """
        closed: List[Dict[str, Any]] = []
        matching_tickets = [
            t for t, p in self.positions.items()
            if p["symbol"].upper() == snapshot.symbol.upper()
        ]

        for ticket in matching_tickets:
            pos = self.positions.get(ticket)
            if not pos:
                continue

            side = pos["side"]
            sl = pos.get("stop_loss")
            tp = pos.get("take_profit")

            if side in (OrderSide.BUY.value, "BUY"):
                # BUY: SL triggers if low touches SL; TP triggers if high touches TP
                if sl is not None and snapshot.low <= sl:
                    res = self.close_position(
                        ticket=ticket,
                        exit_price=sl,
                        exit_time=snapshot.timestamp_utc,
                        exit_reason="STOP_LOSS",
                    )
                    if res:
                        closed.append(res)
                elif tp is not None and snapshot.high >= tp:
                    res = self.close_position(
                        ticket=ticket,
                        exit_price=tp,
                        exit_time=snapshot.timestamp_utc,
                        exit_reason="TAKE_PROFIT",
                    )
                    if res:
                        closed.append(res)
            else:
                # SELL: SL triggers if high touches SL; TP triggers if low touches TP
                if sl is not None and snapshot.high >= sl:
                    res = self.close_position(
                        ticket=ticket,
                        exit_price=sl,
                        exit_time=snapshot.timestamp_utc,
                        exit_reason="STOP_LOSS",
                    )
                    if res:
                        closed.append(res)
                elif tp is not None and snapshot.low <= tp:
                    res = self.close_position(
                        ticket=ticket,
                        exit_price=tp,
                        exit_time=snapshot.timestamp_utc,
                        exit_reason="TAKE_PROFIT",
                    )
                    if res:
                        closed.append(res)

        return closed

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
