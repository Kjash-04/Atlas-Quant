"""
Strategy Validator Module.
Strictly validates StrategySpec to reject ambiguous, unbounded, or unsafe specifications.
"""

from __future__ import annotations

from typing import List
from src.schemas.strategy import StrategySpec, Rule


class ValidationError(Exception):
    """Raised when a StrategySpec violates mathematical, risk, or bounded execution constraints."""
    pass


class StrategyValidator:
    ALLOWED_OPERATORS = {">", "<", ">=", "<=", "==", "!=", "CROSS_ABOVE", "CROSS_BELOW"}

    @classmethod
    def validate(cls, spec: StrategySpec) -> None:
        errors: List[str] = []

        # 1. Rules non-empty
        if not spec.entry_rules:
            errors.append("Entry rules cannot be empty.")
        if not spec.exit_rules:
            errors.append("Exit rules cannot be empty.")

        # 2. Check rule operators
        for idx, rule in enumerate(spec.entry_rules):
            if rule.operator not in cls.ALLOWED_OPERATORS:
                errors.append(f"Invalid entry rule [{idx}] operator: '{rule.operator}'.")
            if rule.lookback < 1:
                errors.append(f"Entry rule [{idx}] lookback must be >= 1.")

        for idx, rule in enumerate(spec.exit_rules):
            if rule.operator not in cls.ALLOWED_OPERATORS:
                errors.append(f"Invalid exit rule [{idx}] operator: '{rule.operator}'.")

        # 3. Bracket order bounds
        if not (0.2 <= spec.stop_loss_atr_mult <= 5.0):
            errors.append(f"Stop loss ATR multiplier {spec.stop_loss_atr_mult} out of bounds [0.2, 5.0].")
        if not (0.5 <= spec.take_profit_rr <= 10.0):
            errors.append(f"Take profit RR {spec.take_profit_rr} out of bounds [0.5, 10.0].")

        # 4. Position sizing risk limits
        risk_fraction = spec.position_sizing.risk_per_trade
        if not (0.001 <= risk_fraction <= 0.03):
            errors.append(f"Risk per trade fraction {risk_fraction} out of bounds [0.001, 0.03] (0.1% to 3.0%).")

        # 5. Risk controls completeness & bounds
        rc = spec.risk_controls
        if rc.max_daily_trades <= 0 or rc.max_daily_trades > 50:
            errors.append(f"max_daily_trades ({rc.max_daily_trades}) must be in range [1, 50].")
        if rc.news_blackout_minutes < 10:
            errors.append(f"news_blackout_minutes ({rc.news_blackout_minutes}) must be >= 10.")
        if rc.max_spread_pips <= 0.0 or rc.max_spread_pips > 10.0:
            errors.append(f"max_spread_pips ({rc.max_spread_pips}) must be in range (0, 10.0].")
        if rc.max_open_positions <= 0 or rc.max_open_positions > 10:
            errors.append(f"max_open_positions ({rc.max_open_positions}) must be in range [1, 10].")
        if not rc.allowed_sessions:
            errors.append("allowed_sessions cannot be empty.")

        # 6. Parameter ranges bounded check
        for param_name, bounds in spec.parameter_ranges.items():
            if not isinstance(bounds, (list, tuple)) or len(bounds) < 1:
                errors.append(f"Parameter '{param_name}' range must be non-empty list of values.")
            elif len(bounds) > 20:
                errors.append(f"Parameter '{param_name}' range exceeds maximum 20 search points (prevent overfitting).")

        if errors:
            raise ValidationError("StrategySpec validation failed:\n" + "\n".join(f"- {e}" for e in errors))
