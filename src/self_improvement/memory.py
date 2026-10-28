"""
Memory Agent & Champion/Challenger Registry.
Maintains experiment database, learning store, and strategy lifecycle versions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from src.core.audit import audit_logger
from src.database.connection import SessionLocal
from src.database.models import LearningModel, StrategyVersionModel
from src.schemas.system import LearningRecord

logger = logging.getLogger(__name__)


class MemoryAgent:
    def __init__(self):
        pass

    def get_champion_version(self, strategy_id: str, db: Optional[Session] = None) -> Optional[StrategyVersionModel]:
        """Fetches current active CHAMPION version for a given strategy family."""
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            return db.query(StrategyVersionModel).filter(
                StrategyVersionModel.strategy_id == strategy_id,
                StrategyVersionModel.status == "CHAMPION"
            ).first()
        finally:
            if own_session:
                db.close()

    def promote_to_champion(
        self,
        strategy_id: str,
        new_champion_version_id: str,
        db: Optional[Session] = None,
    ) -> None:
        """Promotes challenger version to CHAMPION and retires older versions."""
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            # Demote existing champion
            curr_champ = db.query(StrategyVersionModel).filter(
                StrategyVersionModel.strategy_id == strategy_id,
                StrategyVersionModel.status == "CHAMPION"
            ).all()
            for c in curr_champ:
                c.status = "RETIRED"

            # Promote new champion
            target = db.query(StrategyVersionModel).filter(
                StrategyVersionModel.version_id == new_champion_version_id
            ).first()
            if target:
                target.status = "CHAMPION"
                db.commit()
                logger.info(f"Promoted {new_champion_version_id} to CHAMPION status.")
            else:
                logger.error(f"Version {new_champion_version_id} not found to promote.")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to promote champion: {e}")
        finally:
            if own_session:
                db.close()

    def store_learning(
        self,
        strategy_id: str,
        diagnosis: str,
        hypothesis: str,
        diff: str,
        metrics_before: Dict[str, Any],
        metrics_after: Dict[str, Any],
        decision: str,
        reason: str,
        embedding: Optional[List[float]] = None,
        db: Optional[Session] = None,
    ) -> str:
        """Persists learning to learning store."""
        learning_id = f"learn_{uuid.uuid4().hex[:8]}"
        record = LearningRecord(
            learning_id=learning_id,
            strategy_id=strategy_id,
            diagnosis=diagnosis,
            hypothesis=hypothesis,
            diff=diff,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            decision=decision,
            reason=reason,
            embedding=embedding or [],
            timestamp=datetime.now(timezone.utc),
        )
        audit_logger.log_learning(record, db=db)
        return learning_id


memory_agent = MemoryAgent()
