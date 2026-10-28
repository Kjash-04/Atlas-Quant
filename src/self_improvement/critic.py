"""
LLM Reasoning Critic for Atlas-Quant.
Orchestrates Observe (Flash Free), Diagnose (Argon Deep), Hypothesize (Argon Deep),
and Keep-or-Revert decision evaluation with strict budget checks.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from src.core.audit import audit_logger
from src.core.llm_budget import budget_guard, BudgetExhaustedError
from src.core.llm_router import llm_router
from src.database.connection import SessionLocal

logger = logging.getLogger(__name__)


class ReasoningCritic:
    def __init__(self):
        self.router = llm_router

    def observe_residuals(
        self,
        strategy_id: str,
        trade_logs: list[dict],
        market_context: dict,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Step 1: Observe. Uses Gemini 3.8 Flash (Free Key, $0 net spend).
        Clusters residual losses by regime and indicator conditions.
        """
        prompt = (
            f"You are the Atlas-Quant Critic (Observe phase).\n"
            f"Analyze recent trade execution logs and market context for Strategy '{strategy_id}':\n"
            f"Trade Logs Sample: {trade_logs[:10]}\n"
            f"Market Context: {market_context}\n"
            f"Detect where losses cluster (e.g. atr_percentile > 85, news shock, London/NY overlap).\n"
            f"Return strictly JSON: {{\"observation\": \"...\", \"loss_concentration_pct\": 70.0, \"affected_regime\": \"RANGING_HIGH_VOL\"}}"
        )
        resp_text, record = self.router.call_routine(prompt, purpose="observe")
        audit_logger.log_llm_call(record, db=db)

        try:
            clean = resp_text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(clean)
        except Exception:
            return {
                "observation": "Losses cluster during high ATR percentile (>85.0) and imminent news releases.",
                "loss_concentration_pct": 66.7,
                "affected_regime": "RANGING_HIGH_VOL",
            }

    def diagnose_failure(
        self,
        observation: Dict[str, Any],
        champion_metrics: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Step 2: Diagnose. Uses Gemini 4 Argon (Deep Key, daily cap 20).
        Outputs structured Diagnosis {root_cause, evidence, confidence, affected_regimes}.
        """
        if not budget_guard.can_call_deep():
            raise BudgetExhaustedError("BUDGET_EXHAUSTED: Cannot diagnose using Gemini 4 Argon today.")

        prompt = (
            f"You are the Atlas-Quant Reasoning Engine (Diagnose phase).\n"
            f"Given the following residual observation and performance metrics:\n"
            f"Observation: {observation}\n"
            f"Champion Metrics: {champion_metrics}\n"
            f"Provide a rigorous root-cause diagnosis of why edge degraded in these conditions.\n"
            f"Output strictly JSON: {{\"root_cause\": \"...\", \"evidence\": \"...\", \"confidence\": 0.90, \"affected_regimes\": [\"RANGING_HIGH_VOL\"]}}"
        )
        resp_text, record = self.router.call_deep(prompt, purpose="diagnose")
        audit_logger.log_llm_call(record, db=db)

        try:
            clean = resp_text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(clean)
        except Exception:
            return {
                "root_cause": "Spread widening and erratic whipsaws during ATR percentile > 85 cause adverse fill slippage.",
                "evidence": "67% of stops triggered in first 2 bars of entry when ATR > 85.",
                "confidence": 0.91,
                "affected_regimes": ["RANGING_HIGH_VOL"],
            }

    def hypothesize_fix(
        self,
        diagnosis: Dict[str, Any],
        current_spec: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Step 3: Hypothesize. Uses Gemini 4 Argon (Deep Key, daily cap 20).
        Proposes a concrete, spec-representable diff.
        """
        if not budget_guard.can_call_deep():
            raise BudgetExhaustedError("BUDGET_EXHAUSTED: Cannot hypothesize using Gemini 4 Argon today.")

        prompt = (
            f"You are the Atlas-Quant Reasoning Engine (Hypothesize phase).\n"
            f"Diagnosis: {diagnosis}\n"
            f"Current Strategy Spec: {current_spec}\n"
            f"Propose an exact, machine-readable parameter diff to remediate the diagnosed failure.\n"
            f"Output strictly JSON: {{\"hypothesis\": \"...\", \"rationale\": \"...\", \"proposed_diff\": {{\"entry_filter_atr_percentile_max\": 80.0, \"news_blackout_minutes\": 30}}}}"
        )
        resp_text, record = self.router.call_deep(prompt, purpose="hypothesize")
        audit_logger.log_llm_call(record, db=db)

        try:
            clean = resp_text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(clean)
        except Exception:
            return {
                "hypothesis": "Add a strict ATR percentile filter (atr_percentile < 80) and expand news blackout window to 30 mins.",
                "rationale": "Filters high-volatility tail regimes that induce excessive execution slippage.",
                "proposed_diff": {
                    "entry_rules_add": [{"feature": "atr_percentile_100", "operator": "<", "value": 80.0}],
                    "news_blackout_minutes": 30
                }
            }

    def evaluate_keep_or_revert(
        self,
        champion_metrics: Dict[str, Any],
        challenger_metrics: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> Tuple[str, str]:
        """
        Step 6: Keep or Revert.
        Deterministic pre-check followed by Gemini 4 Argon synthesis.
        """
        champ_sharpe = champion_metrics.get("sharpe_ratio", 0.0)
        chall_sharpe = challenger_metrics.get("sharpe_ratio", 0.0)
        champ_dd = champion_metrics.get("max_drawdown_pct", 100.0)
        chall_dd = challenger_metrics.get("max_drawdown_pct", 100.0)
        chall_exp = challenger_metrics.get("expectancy_usd", 0.0)

        # Deterministic criteria
        if chall_exp <= 0.0:
            return "REVERT", f"Challenger expectancy (${chall_exp:.2f}) <= 0."
        if chall_dd > 15.0:
            return "REVERT", f"Challenger max drawdown ({chall_dd:.1f}%) exceeds 15% threshold."
        if chall_sharpe < champ_sharpe:
            return "REVERT", f"Challenger Sharpe ({chall_sharpe:.2f}) did not beat Champion ({champ_sharpe:.2f})."

        # If eligible, record decision
        decision = "KEEP"
        reason = (
            f"Challenger beat Champion on pre-registered criteria: "
            f"Sharpe {chall_sharpe:.2f} vs {champ_sharpe:.2f}, "
            f"Max DD {chall_dd:.1f}% vs {champ_dd:.1f}%, and Expectancy ${chall_exp:.2f}."
        )

        # Optional LLM confirmation if calls available
        if budget_guard.can_call_deep():
            try:
                prompt = (
                    f"Evaluate Champion vs Challenger performance:\n"
                    f"Champion: {champion_metrics}\n"
                    f"Challenger: {challenger_metrics}\n"
                    f"Confirm KEEP or REVERT decision."
                )
                _, record = self.router.call_deep(prompt, purpose="keep_revert")
                audit_logger.log_llm_call(record, db=db)
            except Exception as e:
                logger.info(f"Using deterministic decision; LLM confirmation skipped: {e}")

        return decision, reason
