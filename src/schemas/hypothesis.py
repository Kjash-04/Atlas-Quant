"""
Trading Hypothesis Schema.
Tracks research ideas through the formal validation lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class HypothesisStatus(str, Enum):
    IDEA = "IDEA"
    SPEC = "SPEC"
    CODED = "CODED"
    BACKTESTING = "BACKTESTING"
    VALIDATED = "VALIDATED"
    IMPROVED = "IMPROVED"
    REJECTED = "REJECTED"
    CHAMPION = "CHAMPION"
    RETIRED = "RETIRED"


class Hypothesis(BaseModel):
    id: str = Field(default_factory=lambda: f"hyp-{uuid.uuid4().hex[:8]}")
    natural_language_idea: str
    rationale: str
    regime_scope: List[str] = Field(default_factory=lambda: ["TRENDING_BULL", "TRENDING_BEAR"])
    proposed_indicators: List[str] = Field(default_factory=lambda: ["EMA", "RSI", "ATR"])
    expected_edge: str
    risk_notes: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parent_learning_ids: List[str] = Field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.IDEA
    rejection_reason: Optional[str] = None

    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
