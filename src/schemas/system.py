"""
System Health, Audit, LLM Logs, and Approvals Schemas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class CircuitBreakerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    HALTED = "HALTED"


class LLMCallRecord(BaseModel):
    call_id: str
    model_id: str  # "gemini-3.8-flash" or "gemini-4-argon"
    purpose: str   # "observe", "diagnose", "hypothesize", "coder", "keep_revert"
    prompt_hash: str
    token_count_input: int = 0
    token_count_output: int = 0
    estimated_cost_usd: float = 0.0  # Must be 0.00 for free tier & credits
    cache_hit: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class LearningRecord(BaseModel):
    learning_id: str
    strategy_id: str
    diagnosis: str
    hypothesis: str
    diff: str
    metrics_before: Dict[str, Any]
    metrics_after: Dict[str, Any]
    decision: str  # "KEEP" or "REVERT"
    reason: str
    embedding: List[float] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class SystemHealthRecord(BaseModel):
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    circuit_breaker_status: CircuitBreakerStatus = CircuitBreakerStatus.ACTIVE
    data_feed_ok: bool = True
    broker_connected: bool = True
    db_connected: bool = True
    daily_deep_llm_calls_used: int = 0
    daily_deep_llm_calls_limit: int = 20
    monthly_cloud_budget_spent_usd: float = 0.0
    active_open_positions: int = 0
    current_equity_usd: float = 100000.0
    daily_pnl_pct: float = 0.0
    peak_drawdown_pct: float = 0.0
    active_incidents: List[str] = Field(default_factory=list)


class HumanApprovalRecord(BaseModel):
    approval_id: str
    action: str  # "ENABLE_LIVE_TRADING", "MODIFY_RISK_LIMITS", "ALLOCATE_CAPITAL"
    approved_by: str  # "kheni" or authorized admin
    digital_signature: str
    notes: str
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_revoked: bool = False
