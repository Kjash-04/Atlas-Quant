"""
Trade & Order Schemas.
Deterministic order intents passed into RiskEngine and Execution Adapters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderIntent(BaseModel):
    intent_id: str
    strategy_id: str
    version_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    requested_lots: float
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    max_slippage_pips: float = 2.0
    idempotency_key: str
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("timestamp_utc")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class OrderExecutionResult(BaseModel):
    intent_id: str
    broker_ticket: Optional[int] = None
    symbol: str
    side: OrderSide
    executed_lots: float
    executed_price: float
    spread_paid_pips: float
    slippage_pips: float
    commission_usd: float
    status: str  # "FILLED", "REJECTED", "CANCELLED", "SIMULATED"
    error_message: Optional[str] = None
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("executed_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class TradeRecord(BaseModel):
    trade_id: str
    strategy_id: str
    version_id: str
    symbol: str
    side: OrderSide
    entry_time: datetime
    exit_time: Optional[datetime] = None
    entry_price: float
    exit_price: Optional[float] = None
    lots: float
    pnl_usd: float = 0.0
    pnl_pips: float = 0.0
    commission_usd: float = 0.0
    swap_usd: float = 0.0
    exit_reason: Optional[str] = None  # "TAKE_PROFIT", "STOP_LOSS", "SIGNAL", "CIRCUIT_BREAKER"
    is_paper: bool = True
