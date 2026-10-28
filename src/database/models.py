"""
SQLAlchemy ORM Models for Atlas-Quant.
Persists all market snapshots, hypotheses, strategy versions, backtests, trades,
experiments, LLM calls, health events, and human approvals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from src.database.connection import Base


class MarketSnapshotModel(Base):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), index=True, nullable=False)
    timestamp_utc = Column(DateTime(timezone=True), index=True, nullable=False)
    timeframe = Column(String(10), nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    spread = Column(Float, nullable=False)
    indicators_json = Column(JSON, nullable=False, default=dict)
    news_events_json = Column(JSON, nullable=False, default=list)
    alt_data_json = Column(JSON, nullable=False, default=dict)
    regime_label = Column(String(30), default="UNKNOWN")
    data_hash = Column(String(64), index=True, nullable=False)
    ingested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_symbol_timestamp", "symbol", "timestamp_utc"),
    )


class HypothesisModel(Base):
    __tablename__ = "hypotheses"

    id = Column(String(64), primary_key=True)
    natural_language_idea = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    regime_scope = Column(JSON, nullable=False, default=list)
    proposed_indicators = Column(JSON, nullable=False, default=list)
    expected_edge = Column(Text, nullable=False)
    risk_notes = Column(Text, nullable=False)
    parent_learning_ids = Column(JSON, default=list)
    status = Column(String(30), default="IDEA", index=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class StrategyVersionModel(Base):
    __tablename__ = "strategy_versions"

    version_id = Column(String(64), primary_key=True)
    strategy_id = Column(String(64), index=True, nullable=False)
    parent_version_id = Column(String(64), nullable=True)
    hypothesis_id = Column(String(64), ForeignKey("hypotheses.id"), nullable=False)
    spec_json = Column(JSON, nullable=False)
    python_code = Column(Text, nullable=False)
    code_hash = Column(String(64), nullable=False)
    param_hash = Column(String(64), nullable=False)
    status = Column(String(30), default="SPEC", index=True)  # SPEC, CODED, VALIDATED, CHAMPION, RETIRED
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BacktestRunModel(Base):
    __tablename__ = "backtest_runs"

    run_id = Column(String(64), primary_key=True)
    strategy_id = Column(String(64), index=True, nullable=False)
    version_id = Column(String(64), ForeignKey("strategy_versions.version_id"), nullable=False)
    data_hash = Column(String(64), nullable=False)
    code_hash = Column(String(64), nullable=False)
    param_hash = Column(String(64), nullable=False)
    is_metrics = Column(JSON, nullable=False)
    oos_metrics = Column(JSON, nullable=False)
    test_metrics = Column(JSON, nullable=True)
    walk_forward_json = Column(JSON, default=list)
    robustness_json = Column(JSON, default=dict)
    costs_json = Column(JSON, default=dict)
    passes_champion_criteria = Column(Boolean, default=False)
    rejection_reasons = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ExperimentModel(Base):
    __tablename__ = "experiments"

    experiment_id = Column(String(64), primary_key=True)
    strategy_id = Column(String(64), index=True, nullable=False)
    version_id = Column(String(64), nullable=False)
    parent_version_id = Column(String(64), nullable=True)
    code_hash = Column(String(64), nullable=False)
    param_hash = Column(String(64), nullable=False)
    data_hash = Column(String(64), nullable=False)
    metrics_json = Column(JSON, nullable=False)
    decision = Column(String(20), nullable=False)  # KEEP or REVERT
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LearningModel(Base):
    __tablename__ = "learnings"

    learning_id = Column(String(64), primary_key=True)
    strategy_id = Column(String(64), index=True, nullable=False)
    diagnosis = Column(Text, nullable=False)
    hypothesis = Column(Text, nullable=False)
    diff = Column(Text, nullable=False)
    metrics_before = Column(JSON, nullable=False)
    metrics_after = Column(JSON, nullable=False)
    decision = Column(String(20), nullable=False)  # KEEP or REVERT
    reason = Column(Text, nullable=False)
    embedding = Column(JSON, default=list)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TradeModel(Base):
    __tablename__ = "trades"

    trade_id = Column(String(64), primary_key=True)
    broker_ticket = Column(Integer, nullable=True)
    strategy_id = Column(String(64), index=True, nullable=False)
    version_id = Column(String(64), nullable=False)
    symbol = Column(String(20), index=True, nullable=False)
    side = Column(String(10), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    lots = Column(Float, nullable=False)
    pnl_usd = Column(Float, default=0.0)
    pnl_pips = Column(Float, default=0.0)
    commission_usd = Column(Float, default=0.0)
    swap_usd = Column(Float, default=0.0)
    exit_reason = Column(String(50), nullable=True)
    is_paper = Column(Boolean, default=True)


class LLMCallModel(Base):
    __tablename__ = "llm_calls"

    call_id = Column(String(64), primary_key=True)
    model_id = Column(String(50), nullable=False)  # gemini-3.8-flash or gemini-4-argon
    purpose = Column(String(50), nullable=False)   # observe, diagnose, hypothesize, coder, keep_revert
    prompt_hash = Column(String(64), index=True, nullable=False)
    token_count_input = Column(Integer, default=0)
    token_count_output = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)  # Must be 0.00
    cache_hit = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SystemHealthModel(Base):
    __tablename__ = "system_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp_utc = Column(DateTime(timezone=True), index=True, default=lambda: datetime.now(timezone.utc))
    circuit_breaker_status = Column(String(20), default="ACTIVE")
    data_feed_ok = Column(Boolean, default=True)
    broker_connected = Column(Boolean, default=True)
    db_connected = Column(Boolean, default=True)
    daily_deep_llm_calls_used = Column(Integer, default=0)
    daily_deep_llm_calls_limit = Column(Integer, default=20)
    monthly_cloud_budget_spent_usd = Column(Float, default=0.0)
    active_open_positions = Column(Integer, default=0)
    current_equity_usd = Column(Float, default=100000.0)
    daily_pnl_pct = Column(Float, default=0.0)
    peak_drawdown_pct = Column(Float, default=0.0)
    incidents_json = Column(JSON, default=list)


class ApprovalModel(Base):
    __tablename__ = "approvals"

    approval_id = Column(String(64), primary_key=True)
    action = Column(String(50), nullable=False)  # ENABLE_LIVE_TRADING, MODIFY_RISK_LIMITS
    approved_by = Column(String(100), nullable=False)
    digital_signature = Column(String(128), nullable=False)
    notes = Column(Text, nullable=False)
    approved_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_revoked = Column(Boolean, default=False)
