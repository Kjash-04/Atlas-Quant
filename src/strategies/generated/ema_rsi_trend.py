"""
Strategy Implementation: EMA Trend with RSI Momentum and Volatility Guard.
Generated deterministically from hypothesis:
"Go long when short EMA crosses above long EMA and RSI is not overbought,
but skip trades when volatility is extreme or a high-impact news event is within 30 minutes.
Risk 1% per trade with a 2R target and an ATR-based stop."
"""

from __future__ import annotations

from typing import Tuple
import numpy as np
import pandas as pd

from src.ingestion.indicators import calculate_indicators
from src.schemas.market import MarketSnapshot
from src.schemas.strategy import StrategySpec
from src.strategies.base import BaseStrategy


class EmaRsiTrendStrategy(BaseStrategy):
    def __init__(self, spec: StrategySpec):
        super().__init__(spec)

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates causal indicators."""
        return calculate_indicators(df)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        Signals:
          1: Long entry
         -1: Short entry
          0: Flat / No signal
        """
        signals = pd.Series(0, index=df.index)
        if len(df) < 15:
            return signals

        # Causal feature extraction
        ema_fast = df["ema_20"]
        ema_slow = df["ema_50"]
        rsi = df["rsi_14"]
        atr_pct = df["atr_percentile_100"]

        # Causal cross above (shift 1 compares strictly prior closed bar)
        prev_fast = ema_fast.shift(1)
        prev_slow = ema_slow.shift(1)
        cross_above = (prev_fast <= prev_slow) & (ema_fast > ema_slow)

        # Filters: RSI not overbought (< 70), RSI has positive momentum (> 48), ATR percentile < 85
        long_condition = (
            cross_above
            & (rsi < 70.0)
            & (rsi > 48.0)
            & (atr_pct < 85.0)
        )
        signals[long_condition] = 1

        # Bearish cross below
        cross_below = (prev_fast >= prev_slow) & (ema_fast < ema_slow)
        short_condition = (
            cross_below
            & (rsi > 30.0)
            & (rsi < 52.0)
            & (atr_pct < 85.0)
        )
        signals[short_condition] = -1

        return signals
