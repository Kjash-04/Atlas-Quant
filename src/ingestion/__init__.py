"""
Market data ingestion, adapters, and causal indicator calculations.
"""

from src.ingestion.indicators import calculate_indicators, identify_market_regime, detect_session
from src.ingestion.adapters import (
    BaseAdapter,
    TradingViewWebhookAdapter,
    MT5Adapter,
    NewsCalendarAdapter,
    AlternativeDataAdapter,
)
from src.ingestion.agent import DataIngestionAgent

__all__ = [
    "calculate_indicators",
    "identify_market_regime",
    "detect_session",
    "BaseAdapter",
    "TradingViewWebhookAdapter",
    "MT5Adapter",
    "NewsCalendarAdapter",
    "AlternativeDataAdapter",
    "DataIngestionAgent",
]
