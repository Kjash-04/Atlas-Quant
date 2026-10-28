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
    point_value: float = 100000.0,
    lot_step: float = 0.01,
    min_lot: float = 0.01,
    max_lot: float = 5.0,
) -> float:
    """
    Sizes position so that risking the stop loss distance loses exactly (equity * risk_fraction).
    Formula:
        risk_usd = equity * risk_fraction
        raw_lots = risk_usd / (stop_distance_price * point_value)
        lots = floor(raw_lots / lot_step) * lot_step
    """
    if stop_distance_price <= 0:
        raise ValueError(f"Stop distance must be strictly positive, got {stop_distance_price}")
    if equity <= 0:
        raise ValueError(f"Account equity must be positive, got {equity}")

    risk_usd = equity * risk_fraction
    raw_lots = risk_usd / (stop_distance_price * point_value)
    # Floor to nearest lot step
    quantized_lots = math.floor(raw_lots / lot_step) * lot_step
    # Clip between broker min and max
    final_lots = float(np.clip(quantized_lots, min_lot, max_lot))
    return round(final_lots, 2)
