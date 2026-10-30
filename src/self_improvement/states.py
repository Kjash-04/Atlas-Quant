"""
LangGraph State Definition for Autonomous Self-Improvement.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class SelfImprovementState(TypedDict, total=False):
    # Identifiers
    cycle_id: str
    strategy_id: str
    champion_version_id: str
    challenger_version_id: Optional[str]

    # Step 1: Observe (Gemini 3.8 Flash Free)
    observed_residuals: Dict[str, Any]

    # Step 2: Diagnose (Gemini 4 Argon Deep)
    diagnosis: Dict[str, Any]

    # Step 3: Hypothesize (Gemini 4 Argon Deep)
    hypothesis_diff: Dict[str, Any]

    # Step 4: Experiment (Coder Agent)
    challenger_code_hash: str
    challenger_spec_json: Dict[str, Any]

    # Step 5: Validate (Local compute BacktestAgent)
    champion_metrics: Dict[str, Any]
    challenger_metrics: Dict[str, Any]
    validation_passed: bool

    # Step 6: Keep or Revert (Gemini 4 Argon / Deterministic scorecard)
    decision: str  # "KEEP" or "REVERT"
    reason: str

    # Step 7: Store (MemoryAgent / Gemini 3.8 Flash Free)
    learning_id: Optional[str]

    # Execution control & guardrails
    insufficient_data: bool
    is_budget_exhausted: bool
    consecutive_reverts: int
    error: Optional[str]
    audit_events: List[str]
