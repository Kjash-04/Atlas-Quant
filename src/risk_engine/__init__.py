"""
Risk Engine Package.
Deterministic, pre-trade risk gating layer.
Strictly immutable by the AI self-improvement loop.
"""

from src.risk_engine.rules import RiskGateCheckResult, RiskRuleViolation
from src.risk_engine.sizing import calculate_risk_sized_lots
from src.risk_engine.engine import RiskEngine, risk_engine

__all__ = [
    "RiskGateCheckResult",
    "RiskRuleViolation",
    "calculate_risk_sized_lots",
    "RiskEngine",
    "risk_engine",
]
