"""
Deterministic Strategy Specification Schema.
Strict, machine-readable Python rules with zero ambiguous English interpretation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class RuleLogic(str, Enum):
    AND = "AND"
    OR = "OR"
    WEIGHTED_THRESHOLD = "WEIGHTED_THRESHOLD"


class Rule(BaseModel):
    feature: str  # e.g., "ema_20", "rsi_14", "close", "atr_percentile_100"
    operator: str  # e.g., ">", "<", ">=", "<=", "CROSS_ABOVE", "CROSS_BELOW"
    value: Any  # e.g., 50.0, "ema_50", 70.0
    lookback: int = 1
    weight: float = 1.0


class PositionSizingSpec(BaseModel):
    model: str = "fixed_fractional"
    risk_per_trade: float = 0.01
    max_position_pct: float = 0.05
    lot_step: float = 0.01


class RiskControlsSpec(BaseModel):
    max_daily_trades: int = 10
    news_blackout_minutes: int = 30
    max_spread_pips: float = 2.5
    allowed_sessions: List[str] = Field(default_factory=lambda: ["LONDON", "NEW_YORK"])
    max_correlated_positions: int = 1
    max_open_positions: int = 3


class StrategySpec(BaseModel):
    strategy_id: str
    version: str = "v1.0.0"
    parent_version: Optional[str] = None
    hypothesis_id: str
    status: str = "SPEC"  # SPEC, CODED, VALIDATED, CHAMPION, RETIRED
    universe: List[str] = Field(default_factory=lambda: ["EURUSD", "GBPUSD"])
    timeframe: str = "M15"
    required_indicators: List[str] = Field(default_factory=lambda: ["EMA_20", "EMA_50", "RSI_14", "ATR_14"])
    
    # Execution Rules
    entry_logic: RuleLogic = RuleLogic.AND
    entry_rules: List[Rule]
    exit_logic: RuleLogic = RuleLogic.OR
    exit_rules: List[Rule]
    
    # Bracket Orders
    stop_loss_atr_mult: float = 1.5
    take_profit_rr: float = 2.0  # Reward-to-Risk ratio
    trailing_stop_atr_mult: Optional[float] = None
    
    # Sizing & Controls
    position_sizing: PositionSizingSpec = Field(default_factory=PositionSizingSpec)
    risk_controls: RiskControlsSpec = Field(default_factory=RiskControlsSpec)
    parameter_ranges: Dict[str, List[Any]] = Field(default_factory=dict)
    invalidation_rules: List[str] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    code_hash: str = ""

    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    def compute_spec_hash(self) -> str:
        dump = self.model_dump(exclude={"code_hash", "created_at"}, mode="json")
        serialized = json.dumps(dump, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
