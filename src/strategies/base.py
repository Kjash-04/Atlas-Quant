"""
Base Quantitative Strategy Interface.
All executable strategies must subclass BaseStrategy and strictly adhere to deterministic rules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
import numpy as np
import pandas as pd

from src.schemas.market import MarketSnapshot
from src.schemas.strategy import StrategySpec


class BaseStrategy(ABC):
    def __init__(self, spec: StrategySpec):
        self.spec = spec
        self.strategy_id = spec.strategy_id
        self.version = spec.version

    @abstractmethod
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Computes all required causal indicators on incoming historical bars."""
        pass

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        Generates trading signals strictly from preceding bars (causal).
        Returns:
            pd.Series with values:
                1  = Long Entry Signal
               -1  = Short Entry Signal
                0  = Neutral / Flat
        """
        pass

    def size_position(self, equity: float, atr: float, symbol_info: Optional[Dict[str, Any]] = None) -> float:
        """
        Calculates position sizing according to spec.
        Uses fixed fractional risk: Risk exactly spec.risk_per_trade of equity.
        """
        info = symbol_info or {}
        point_value = float(info.get("point_value", 100000.0))  # Standard forex lot
        lot_step = float(self.spec.position_sizing.lot_step)
        risk_per_trade = float(self.spec.position_sizing.risk_per_trade)
        stop_mult = float(self.spec.stop_loss_atr_mult)

        risk_amount_usd = equity * risk_per_trade
        stop_distance_price = max(atr * stop_mult, 0.0001)

        # Lot calculation: risk_amount / (stop_distance * point_value)
        raw_lots = risk_amount_usd / (stop_distance_price * point_value)
        # Round down to broker lot step
        lots = np.floor(raw_lots / lot_step) * lot_step
        min_lot = float(info.get("min_lot", 0.01))
        max_lot = float(info.get("max_lot", 5.0))
        return float(np.clip(lots, min_lot, max_lot))

    def risk_filters(self, snapshot: MarketSnapshot) -> Tuple[bool, str]:
        """
        Evaluates pre-trade strategy filters before generating an order intent.
        Checks:
        1. Spread threshold
        2. Session allowance
        3. Imminent high-impact news blackout
        4. Extreme volatility threshold
        """
        controls = self.spec.risk_controls

        # 1. Spread check
        spread_pips = snapshot.spread * 10000.0  # 4-digit pips
        if spread_pips > controls.max_spread_pips:
            return False, f"Spread {spread_pips:.2f} pips exceeds threshold {controls.max_spread_pips} pips"

        # 2. Session check
        current_session = snapshot.indicators.session
        if controls.allowed_sessions and current_session not in controls.allowed_sessions and "ALL" not in controls.allowed_sessions:
            return False, f"Session '{current_session}' not in allowed list: {controls.allowed_sessions}"

        # 3. News blackout check
        for news in snapshot.news_events:
            if news.impact == "HIGH" and news.minutes_until <= controls.news_blackout_minutes:
                return False, f"High-impact news '{news.title}' within {news.minutes_until:.1f}m (blackout {controls.news_blackout_minutes}m)"

        # 4. Volatility regime check
        if snapshot.indicators.atr_percentile_100 and snapshot.indicators.atr_percentile_100 > 90.0:
            return False, f"Extreme volatility: ATR percentile {snapshot.indicators.atr_percentile_100:.1f} > 90.0"

        return True, "PASSED"
