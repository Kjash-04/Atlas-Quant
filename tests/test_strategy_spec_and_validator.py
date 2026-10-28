"""
Unit Tests: Strategy Specification & Validator.
Ensures invalid, unbounded, or risk-deficient specs are rejected.
"""

from __future__ import annotations

import pytest

from src.schemas.hypothesis import Hypothesis
from src.schemas.strategy import StrategySpec, Rule
from src.strategies.coder_agent import StrategyCoderAgent
from src.strategies.validator import StrategyValidator, ValidationError


def test_valid_spec_passes(sample_strategy_spec):
    StrategyValidator.validate(sample_strategy_spec)


def test_validator_rejects_empty_rules(sample_strategy_spec):
    bad_spec = sample_strategy_spec.model_copy(deep=True)
    bad_spec.entry_rules = []
    with pytest.raises(ValidationError, match="Entry rules cannot be empty"):
        StrategyValidator.validate(bad_spec)


def test_validator_rejects_unbounded_risk(sample_strategy_spec):
    bad_spec = sample_strategy_spec.model_copy(deep=True)
    bad_spec.position_sizing.risk_per_trade = 0.08  # 8% risk exceeds 3% ceiling
    with pytest.raises(ValidationError, match="Risk per trade fraction"):
        StrategyValidator.validate(bad_spec)


def test_validator_rejects_missing_sessions(sample_strategy_spec):
    bad_spec = sample_strategy_spec.model_copy(deep=True)
    bad_spec.risk_controls.allowed_sessions = []
    with pytest.raises(ValidationError, match="allowed_sessions cannot be empty"):
        StrategyValidator.validate(bad_spec)


def test_coder_agent_hypothesis_conversion(db_session):
    coder = StrategyCoderAgent()
    hyp = Hypothesis(
        natural_language_idea=(
            "Go long when short EMA crosses above long EMA and RSI is not overbought, "
            "but skip trades when volatility is extreme or a high-impact news event is within 30 minutes. "
            "Risk 1% per trade with a 2R target and an ATR-based stop."
        ),
        rationale="Trend continuation with volatility guard",
        expected_edge="Positive expectancy in trending bull regimes",
        risk_notes="Stop loss at 1.5 ATR",
    )
    spec, code = coder.convert_hypothesis_to_spec(hyp, db=db_session)
    assert spec.strategy_id.startswith("strat_")
    assert "class Strategy_" in code
    assert spec.code_hash is not None
    assert len(spec.code_hash) == 64
