"""
Base Execution Adapter Interface.
Abstracts communication with brokers and paper trading simulation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from src.schemas.market import MarketSnapshot
from src.schemas.trade import OrderExecutionResult, OrderIntent


class BaseExecutionAdapter(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def send_order(
        self,
        intent: OrderIntent,
        approved_lots: float,
        snapshot: Optional[MarketSnapshot] = None,
    ) -> OrderExecutionResult:
        pass

    @abstractmethod
    def cancel_order(self, ticket: int) -> bool:
        pass

    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_open_positions(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def flatten_all_positions(self) -> int:
        pass

    def close_position(
        self,
        ticket: int,
        exit_price: float,
        exit_time: Optional[Any] = None,
        exit_reason: str = "MANUAL",
    ) -> Optional[Dict[str, Any]]:
        """Optional hook to close a specific position by ticket with realized PnL."""
        return None

    def tick_positions(self, snapshot: MarketSnapshot) -> List[Dict[str, Any]]:
        """Optional hook to evaluate SL/TP triggers against market snapshots."""
        return []
