"""
Base Execution Adapter Interface.
Abstracts communication with brokers and paper trading simulation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from src.schemas.trade import OrderExecutionResult, OrderIntent


class BaseExecutionAdapter(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def send_order(self, intent: OrderIntent, approved_lots: float) -> OrderExecutionResult:
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
