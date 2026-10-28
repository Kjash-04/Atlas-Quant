"""
Immutable Audit Logging Module.
Persists every hypothesis, code diff, parameter set, backtest result, decision,
trade, LLM call, and health event with timestamps, version IDs, parent IDs, and cryptographic hashes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.models import (
    ExperimentModel,
    LLMCallModel,
    LearningModel,
    SystemHealthModel,
    TradeModel,
)
from src.schemas.system import LLMCallRecord, LearningRecord

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self):
        pass

    def log_llm_call(self, record: LLMCallRecord, db: Optional[Session] = None) -> None:
        """Persists LLM call record with model ID, hashes, token counts, and zero-spend tracking."""
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            model = LLMCallModel(
                call_id=record.call_id,
                model_id=record.model_id,
                purpose=record.purpose,
                prompt_hash=record.prompt_hash,
                token_count_input=record.token_count_input,
                token_count_output=record.token_count_output,
                estimated_cost_usd=record.estimated_cost_usd,
                cache_hit=record.cache_hit,
                created_at=record.created_at,
            )
            db.add(model)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to log LLM call to DB: {e}")
        finally:
            if own_session:
                db.close()

    def log_experiment(
        self,
        experiment_id: str,
        strategy_id: str,
        version_id: str,
        parent_version_id: Optional[str],
        code_hash: str,
        param_hash: str,
        data_hash: str,
        metrics: Dict[str, Any],
        decision: str,
        reason: str,
        db: Optional[Session] = None,
    ) -> None:
        """Logs experiment lifecycle decision (KEEP/REVERT) with complete hashes."""
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            exp = ExperimentModel(
                experiment_id=experiment_id,
                strategy_id=strategy_id,
                version_id=version_id,
                parent_version_id=parent_version_id,
                code_hash=code_hash,
                param_hash=param_hash,
                data_hash=data_hash,
                metrics_json=metrics,
                decision=decision,
                reason=reason,
                created_at=datetime.now(timezone.utc),
            )
            db.add(exp)
            db.commit()
            logger.info(f"Experiment {experiment_id} logged: Decision={decision}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to log experiment: {e}")
        finally:
            if own_session:
                db.close()

    def log_learning(self, record: LearningRecord, db: Optional[Session] = None) -> None:
        """Logs structured diagnostic and hypothesis learning."""
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            model = LearningModel(
                learning_id=record.learning_id,
                strategy_id=record.strategy_id,
                diagnosis=record.diagnosis,
                hypothesis=record.hypothesis,
                diff=record.diff,
                metrics_before=record.metrics_before,
                metrics_after=record.metrics_after,
                decision=record.decision,
                reason=record.reason,
                embedding=record.embedding,
                timestamp=record.timestamp,
            )
            db.add(model)
            db.commit()
            logger.info(f"Learning {record.learning_id} persisted.")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to log learning: {e}")
        finally:
            if own_session:
                db.close()


audit_logger = AuditLogger()
