"""
Quantitative Research Agent.
Generates falsifiable hypotheses from market snapshot streams and historical learnings
using Gemini 3.8 Flash (Free Key, $0 net spend).
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from src.core.audit import audit_logger
from src.core.llm_router import llm_router
from src.database.connection import SessionLocal
from src.database.models import HypothesisModel, LearningModel
from src.research.prompt_templates import (
    RESEARCH_HYPOTHESIS_SYSTEM_PROMPT,
    RESEARCH_HYPOTHESIS_USER_PROMPT_TEMPLATE,
)
from src.schemas.hypothesis import Hypothesis, HypothesisStatus
from src.schemas.market import MarketSnapshot

logger = logging.getLogger(__name__)


class ResearchAgent:
    def __init__(self):
        self.router = llm_router

    def generate_hypothesis(
        self,
        snapshot: MarketSnapshot,
        db: Optional[Session] = None,
        parent_learning_ids: Optional[List[str]] = None,
    ) -> Hypothesis:
        """
        Synthesizes snapshot data and past learnings to emit a new Hypothesis.
        """
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True

        try:
            # Gather past learnings
            parent_learning_ids = parent_learning_ids or []
            learnings_text = "No prior failures or learnings recorded."
            if parent_learning_ids:
                learnings_models = db.query(LearningModel).filter(LearningModel.learning_id.in_(parent_learning_ids)).all()
                if learnings_models:
                    learnings_text = "\n".join([f"- Learning {l.learning_id}: Diagnosis: {l.diagnosis} -> Fix: {l.hypothesis}" for l in learnings_models])

            ind = snapshot.indicators
            ind_summary = f"EMA20={ind.ema_20}, EMA50={ind.ema_50}, RSI14={ind.rsi_14}, ATR14={ind.atr_14}, ATR_pct={ind.atr_percentile_100}, Session={ind.session}"

            user_prompt = RESEARCH_HYPOTHESIS_USER_PROMPT_TEMPLATE.format(
                symbol=snapshot.symbol,
                close=snapshot.close,
                indicators_summary=ind_summary,
                regime=snapshot.regime_label.value,
                learnings_summary=learnings_text,
            )
            full_prompt = f"{RESEARCH_HYPOTHESIS_SYSTEM_PROMPT}\n\n{user_prompt}"

            # Call Gemini 3.8 Flash via Free Key
            response_text, record = self.router.call_routine(full_prompt, purpose="research")
            audit_logger.log_llm_call(record, db=db)

            # Parse JSON
            try:
                # Clean markdown blocks if present
                clean_text = response_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                parsed = json.loads(clean_text.strip())
            except Exception as e:
                logger.warning(f"Failed to parse research LLM response as JSON ({e}), using structured default.")
                parsed = {
                    "natural_language_idea": (
                        "Go long when short EMA crosses above long EMA and RSI is not overbought, "
                        "but skip trades when volatility is extreme or a high-impact news event is within 30 minutes. "
                        "Risk 1% per trade with a 2R target and an ATR-based stop."
                    ),
                    "rationale": "Trend continuation supported by momentum with volatility and news shock avoidance.",
                    "regime_scope": ["TRENDING_BULL"],
                    "proposed_indicators": ["EMA_20", "EMA_50", "RSI_14", "ATR_14"],
                    "expected_edge": "Captures established trends while filtering out noise and spread spikes.",
                    "risk_notes": "Stop loss at 1.5 ATR. Mandatory news blackout 30 mins."
                }

            hypothesis = Hypothesis(
                natural_language_idea=parsed.get("natural_language_idea", ""),
                rationale=parsed.get("rationale", ""),
                regime_scope=parsed.get("regime_scope", ["TRENDING_BULL", "TRENDING_BEAR"]),
                proposed_indicators=parsed.get("proposed_indicators", ["EMA_20", "EMA_50", "RSI_14", "ATR_14"]),
                expected_edge=parsed.get("expected_edge", ""),
                risk_notes=parsed.get("risk_notes", ""),
                parent_learning_ids=parent_learning_ids,
                status=HypothesisStatus.IDEA,
            )

            # Persist Hypothesis
            hyp_model = HypothesisModel(
                id=hypothesis.id,
                natural_language_idea=hypothesis.natural_language_idea,
                rationale=hypothesis.rationale,
                regime_scope=hypothesis.regime_scope,
                proposed_indicators=hypothesis.proposed_indicators,
                expected_edge=hypothesis.expected_edge,
                risk_notes=hypothesis.risk_notes,
                parent_learning_ids=hypothesis.parent_learning_ids,
                status=hypothesis.status.value,
                created_at=hypothesis.created_at,
            )
            db.add(hyp_model)
            db.commit()
            logger.info(f"ResearchAgent successfully generated & stored Hypothesis: {hypothesis.id}")
            return hypothesis

        except Exception as e:
            db.rollback()
            logger.error(f"Error in ResearchAgent: {e}")
            raise
        finally:
            if own_session:
                db.close()


research_agent = ResearchAgent()
