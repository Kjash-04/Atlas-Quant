"""
Realistic Execution Cost Model.
Accounts for commissions, time-varying spreads, volatility-proportional slippage, and overnight financing.
"""

from __future__ import annotations

from typing import Dict, Tuple


class RealisticCostModel:
    def __init__(
        self,
        commission_per_lot: float = 3.50,
        default_spread_pips: float = 1.2,
        slippage_base_pips: float = 0.5,
        slippage_vol_factor: float = 0.05,
        daily_swap_long_pct: float = -0.00015,
        daily_swap_short_pct: float = 0.00005,
    ):
        self.commission_per_lot = commission_per_lot
        self.default_spread_pips = default_spread_pips
        self.slippage_base_pips = slippage_base_pips
        self.slippage_vol_factor = slippage_vol_factor
        self.daily_swap_long_pct = daily_swap_long_pct
        self.daily_swap_short_pct = daily_swap_short_pct

    def compute_trade_costs(
        self,
        lots: float,
        entry_price: float,
        exit_price: float,
        side: str,
        atr: float,
        session: str = "LONDON",
        bars_held: int = 1,
        timeframe_minutes: int = 15,
    ) -> Tuple[float, float, float, float, Dict[str, float]]:
        """
        Calculates all friction costs in USD.
        Returns:
            (effective_entry_price, effective_exit_price, total_cost_usd, slippage_pips, breakdown_dict)
        """
        pip_size = 0.0001  # Standard forex 4-digit pip
        point_value = 100000.0  # $10 per pip per 1.0 lot

        # 1. Session-dependent spread
        spread_pips = self.default_spread_pips
        if session == "OFF_HOURS":
            spread_pips *= 2.0
        elif session == "OVERLAP_LDN_NY":
            spread_pips *= 0.85

        # 2. Volatility-proportional slippage
        vol_slippage_pips = (atr / pip_size) * self.slippage_vol_factor
        total_slippage_pips = self.slippage_base_pips + vol_slippage_pips

        # Apply slippage & half spread to prices
        entry_penalty_price = (spread_pips / 2.0 + total_slippage_pips) * pip_size
        exit_penalty_price = (spread_pips / 2.0 + total_slippage_pips) * pip_size

        if side.upper() == "BUY":
            effective_entry = entry_price + entry_penalty_price
            effective_exit = exit_price - exit_penalty_price
        else:
            effective_entry = entry_price - entry_penalty_price
            effective_exit = exit_price + exit_penalty_price

        # Monetary friction totals
        commission_usd = self.commission_per_lot * lots * 2.0  # Round-turn
        spread_usd = spread_pips * lots * 10.0
        slippage_usd = (total_slippage_pips * 2.0) * lots * 10.0

        # Swap / financing
        days_held = (bars_held * timeframe_minutes) / (24.0 * 60.0)
        swap_rate = self.daily_swap_long_pct if side.upper() == "BUY" else self.daily_swap_short_pct
        swap_usd = entry_price * lots * point_value * swap_rate * days_held

        total_cost_usd = commission_usd + spread_usd + slippage_usd + abs(min(0.0, swap_usd))

        breakdown = {
            "commission_usd": commission_usd,
            "spread_usd": spread_usd,
            "slippage_usd": slippage_usd,
            "swap_usd": swap_usd,
            "total_friction_usd": total_cost_usd,
        }
        return effective_entry, effective_exit, total_cost_usd, total_slippage_pips, breakdown
