"""
Position Sizing Module.
Calculates lot sizing based on account equity, stop distance, and fixed fractional risk.
"""

from __future__ import annotations

import math
import numpy as np


def calculate_risk_sized_lots(
    equity: float,
    stop_distance_price: float,
    risk_fraction: float = 0.01,
    current_price: float = 1.0,
    max_position_equity_pct: float = 0.05,
    point_value: float = 100000.0,
    lot_step: float = 0.01,
    min_lot: float = 0.01,
    max_lot: float = 5.0,
) -> float:
    """
    Sizes position so that:
    1. Risking the stop loss distance loses at most (equity * risk_fraction).
    2. Total notional exposure does not exceed (equity * max_position_equity_pct).
       Notional value = lots * current_price * point_value.
       Max lots by notional = (equity * max_position_equity_pct) / (current_price * point_value).
    """
    if stop_distance_price <= 0:
        raise ValueError(f"Stop distance must be strictly positive, got {stop_distance_price}")
    if equity <= 0:
        raise ValueError(f"Account equity must be positive, got {equity}")
    if current_price <= 0:
        current_price = 1.0

    # 1. Stop-Loss Risk Sizing
    risk_usd = equity * risk_fraction
    raw_lots = risk_usd / (stop_distance_price * point_value)

    # 2. Maximum Nominal Position Exposure Sizing (e.g. 5% max exposure)
    max_notional_usd = equity * max_position_equity_pct
    max_lots_by_notional = max_notional_usd / (current_price * point_value)

    # Bound by notional cap
    bounded_lots = min(raw_lots, max_lots_by_notional)

    # Floor to nearest lot step
    quantized_lots = math.floor(bounded_lots / lot_step) * lot_step

    if quantized_lots < min_lot:
        return 0.0

    final_lots = float(np.clip(quantized_lots, min_lot, max_lot))
    return round(final_lots, 2)
