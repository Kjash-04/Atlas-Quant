"""
Atlas-Quant FastAPI Production Control Plane.
Exposes RESTful endpoints for health telemetry, snapshots, research, backtesting,
trade execution, LLM call auditing, and administrative safety controls.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.config import settings
from src.database.connection import get_db, init_db
from src.database.models import (
    ApprovalModel,
    BacktestRunModel,
    ExperimentModel,
    HypothesisModel,
    LLMCallModel,
    LearningModel,
    MarketSnapshotModel,
    StrategyVersionModel,
    TradeModel,
)
from src.execution.agent import execution_agent
from src.ingestion.adapters import TradingViewWebhookAdapter
from src.monitoring.alerts import alert_dispatcher
from src.monitoring.health import health_monitor
from src.research.agent import research_agent
from src.risk_engine.engine import risk_engine
from src.schemas.market import MarketSnapshot
from src.schemas.trade import OrderExecutionResult, OrderIntent

# Initialize FastAPI App
app = FastAPI(
    title="Atlas-Quant Autonomous Research & Trading API",
    description="Multi-AI-Agent Quantitative Research and Risk-Controlled Execution Engine.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Ensure database schema is created on application start."""
    init_db()


# ------------------------------------------------------------------------------
# Request Bodies
# ------------------------------------------------------------------------------
class KillRequest(BaseModel):
    reason: str
    admin_token: str


class ResetCircuitBreakerRequest(BaseModel):
    admin_token: str


class ApproveLiveRequest(BaseModel):
    approved_by: str
    digital_signature: str
    notes: str


# ------------------------------------------------------------------------------
# Root & Health Endpoints
# ------------------------------------------------------------------------------
@app.get("/")
def get_root():
    return {
        "project": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "paper_trading": settings.PAPER_TRADING,
        "disclaimer": settings.RISK_DISCLAIMER,
        "docs_url": "/docs",
    }


@app.get("/health")
def get_system_health(db: Session = Depends(get_db)):
    health_record = health_monitor.check_health(db=db)
    return health_record.model_dump(mode="json")


# ------------------------------------------------------------------------------
# Data Plane: Snapshots
# ------------------------------------------------------------------------------
@app.get("/snapshots")
def list_snapshots(
    symbol: Optional[str] = None,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(MarketSnapshotModel)
    if symbol:
        query = query.filter(MarketSnapshotModel.symbol == symbol.upper())
    snapshots = query.order_by(MarketSnapshotModel.timestamp_utc.desc()).limit(limit).all()
    return [
        {
            "id": s.id,
            "symbol": s.symbol,
            "timestamp_utc": s.timestamp_utc.isoformat(),
            "timeframe": s.timeframe,
            "open": s.open,
            "high": s.high,
            "low": s.low,
            "close": s.close,
            "volume": s.volume,
            "spread": s.spread,
            "regime_label": s.regime_label,
            "data_hash": s.data_hash,
            "indicators": s.indicators_json,
        }
        for s in snapshots
    ]


@app.post("/snapshots", status_code=status.HTTP_201_CREATED)
def ingest_tradingview_webhook(payload: Dict[str, Any]):
    """Ingests TradingView alert webhook, parses snapshot, persists and publishes."""
    adapter = TradingViewWebhookAdapter()
    snapshot = adapter.ingest(payload)
    if not snapshot:
        raise HTTPException(status_code=400, detail="Invalid TradingView webhook format")
    return {"status": "INGESTED", "data_hash": snapshot.data_hash, "symbol": snapshot.symbol}


# ------------------------------------------------------------------------------
# Research Plane: Hypotheses
# ------------------------------------------------------------------------------
@app.get("/hypotheses")
def list_hypotheses(limit: int = Query(50, le=100), db: Session = Depends(get_db)):
    records = db.query(HypothesisModel).order_by(HypothesisModel.created_at.desc()).limit(limit).all()
    return [
        {
            "id": h.id,
            "idea": h.natural_language_idea,
            "rationale": h.rationale,
            "regimes": h.regime_scope,
            "indicators": h.proposed_indicators,
            "status": h.status,
            "created_at": h.created_at.isoformat(),
        }
        for h in records
    ]


@app.post("/hypotheses/generate")
def generate_hypothesis_endpoint(symbol: str = "EURUSD", db: Session = Depends(get_db)):
    """Triggers ResearchAgent using the latest market snapshot."""
    latest_snap = db.query(MarketSnapshotModel).filter(MarketSnapshotModel.symbol == symbol.upper()).order_by(MarketSnapshotModel.timestamp_utc.desc()).first()
    if not latest_snap:
        # Create baseline snapshot for demonstration
        adapter = TradingViewWebhookAdapter()
        snap_obj = adapter.ingest({"symbol": symbol, "close": 1.0850, "timestamp": datetime.now(timezone.utc).isoformat()})
    else:
        from src.schemas.market import IndicatorSet, RegimeLabel
        snap_obj = MarketSnapshot(
            symbol=latest_snap.symbol,
            timestamp_utc=latest_snap.timestamp_utc,
            timeframe=latest_snap.timeframe,
            open=latest_snap.open,
            high=latest_snap.high,
            low=latest_snap.low,
            close=latest_snap.close,
            volume=latest_snap.volume,
            spread=latest_snap.spread,
            indicators=IndicatorSet(**latest_snap.indicators_json),
            regime_label=RegimeLabel(latest_snap.regime_label) if latest_snap.regime_label in RegimeLabel._value2member_map_ else RegimeLabel.UNKNOWN,
        )

    hyp = research_agent.generate_hypothesis(snap_obj, db=db)
    return hyp.model_dump(mode="json")


# ------------------------------------------------------------------------------
# Strategy Plane: Strategies & Versions
# ------------------------------------------------------------------------------
@app.get("/strategies")
def list_strategies(limit: int = Query(50, le=100), db: Session = Depends(get_db)):
    versions = db.query(StrategyVersionModel).order_by(StrategyVersionModel.created_at.desc()).limit(limit).all()
    return [
        {
            "version_id": v.version_id,
            "strategy_id": v.strategy_id,
            "status": v.status,
            "code_hash": v.code_hash,
            "param_hash": v.param_hash,
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ]


# ------------------------------------------------------------------------------
# Backtest Plane: Backtest Runs & Metrics
# ------------------------------------------------------------------------------
@app.get("/backtests")
def list_backtests(limit: int = Query(50, le=100), db: Session = Depends(get_db)):
    runs = db.query(BacktestRunModel).order_by(BacktestRunModel.created_at.desc()).limit(limit).all()
    return [
        {
            "run_id": r.run_id,
            "strategy_id": r.strategy_id,
            "version_id": r.version_id,
            "is_metrics": r.is_metrics,
            "oos_metrics": r.oos_metrics,
            "passes_champion_criteria": r.passes_champion_criteria,
            "rejection_reasons": r.rejection_reasons,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


# ------------------------------------------------------------------------------
# Memory & Learning Plane: Experiments & Learnings
# ------------------------------------------------------------------------------
@app.get("/experiments")
def list_experiments(limit: int = Query(50, le=100), db: Session = Depends(get_db)):
    exps = db.query(ExperimentModel).order_by(ExperimentModel.created_at.desc()).limit(limit).all()
    return [
        {
            "experiment_id": e.experiment_id,
            "strategy_id": e.strategy_id,
            "version_id": e.version_id,
            "decision": e.decision,
            "reason": e.reason,
            "metrics": e.metrics_json,
            "code_hash": e.code_hash,
            "created_at": e.created_at.isoformat(),
        }
        for e in exps
    ]


@app.get("/learnings")
def list_learnings(limit: int = Query(50, le=100), db: Session = Depends(get_db)):
    learnings = db.query(LearningModel).order_by(LearningModel.timestamp.desc()).limit(limit).all()
    return [
        {
            "learning_id": l.learning_id,
            "strategy_id": l.strategy_id,
            "diagnosis": l.diagnosis,
            "hypothesis": l.hypothesis,
            "diff": l.diff,
            "decision": l.decision,
            "reason": l.reason,
            "timestamp": l.timestamp.isoformat(),
        }
        for l in learnings
    ]


# ------------------------------------------------------------------------------
# Governance & Audit Plane: LLM Calls
# ------------------------------------------------------------------------------
@app.get("/llm-calls")
def list_llm_calls(limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    calls = db.query(LLMCallModel).order_by(LLMCallModel.created_at.desc()).limit(limit).all()
    return [
        {
            "call_id": c.call_id,
            "model_id": c.model_id,
            "purpose": c.purpose,
            "prompt_hash": c.prompt_hash,
            "token_count_input": c.token_count_input,
            "token_count_output": c.token_count_output,
            "estimated_cost_usd": c.estimated_cost_usd,
            "cache_hit": c.cache_hit,
            "created_at": c.created_at.isoformat(),
        }
        for c in calls
    ]


# ------------------------------------------------------------------------------
# Execution Plane: Orders & Metrics
# ------------------------------------------------------------------------------
@app.get("/orders")
def list_orders(limit: int = Query(50, le=100), db: Session = Depends(get_db)):
    trades = db.query(TradeModel).order_by(TradeModel.entry_time.desc()).limit(limit).all()
    return [
        {
            "trade_id": t.trade_id,
            "broker_ticket": t.broker_ticket,
            "symbol": t.symbol,
            "side": t.side,
            "entry_time": t.entry_time.isoformat(),
            "entry_price": t.entry_price,
            "lots": t.lots,
            "pnl_usd": t.pnl_usd,
            "is_paper": t.is_paper,
        }
        for t in trades
    ]


@app.post("/orders")
def submit_order_intent(intent: OrderIntent, db: Session = Depends(get_db)):
    """
    Submits an order intent to the ExecutionAgent.
    Strictly gates through RiskEngine before reaching any broker.
    """
    # Fetch latest snapshot
    latest = db.query(MarketSnapshotModel).filter(MarketSnapshotModel.symbol == intent.symbol).order_by(MarketSnapshotModel.timestamp_utc.desc()).first()
    if not latest:
        # Create default live snapshot
        from src.schemas.market import IndicatorSet, RegimeLabel
        snapshot = MarketSnapshot(
            symbol=intent.symbol,
            timestamp_utc=datetime.now(timezone.utc),
            timeframe="M15",
            open=1.0850, high=1.0860, low=1.0845, close=1.0855, volume=500.0, spread=0.00015,
            indicators=IndicatorSet(session="LONDON", atr_percentile_100=50.0),
            regime_label=RegimeLabel.TRENDING_BULL,
        )
    else:
        from src.schemas.market import IndicatorSet, RegimeLabel
        snapshot = MarketSnapshot(
            symbol=latest.symbol,
            timestamp_utc=latest.timestamp_utc,
            timeframe=latest.timeframe,
            open=latest.open, high=latest.high, low=latest.low, close=latest.close,
            volume=latest.volume, spread=latest.spread,
            indicators=IndicatorSet(**latest.indicators_json),
            regime_label=RegimeLabel(latest.regime_label) if latest.regime_label in RegimeLabel._value2member_map_ else RegimeLabel.UNKNOWN,
        )

    result = execution_agent.process_order_intent(intent, snapshot=snapshot, db=db)
    return result.model_dump(mode="json")


@app.get("/metrics")
def get_metrics_summary(db: Session = Depends(get_db)):
    account = execution_agent.adapter.get_account_info()
    positions = execution_agent.adapter.get_open_positions()
    total_trades = db.query(TradeModel).count()
    return {
        "account": account,
        "open_positions": positions,
        "total_trades_count": total_trades,
        "circuit_status": risk_engine.circuit_status.value,
        "kill_switch_engaged": risk_engine.kill_switch_engaged,
    }


# ------------------------------------------------------------------------------
# Administrative & Emergency Safety Controls
# ------------------------------------------------------------------------------
@app.post("/admin/kill")
def emergency_kill(req: KillRequest):
    """Emergency kill switch endpoint: flattens positions and halts engine."""
    if req.admin_token != "EMERGENCY_KILL_AUTHORIZED":
        raise HTTPException(status_code=403, detail="Invalid admin authorization token")
    closed = execution_agent.emergency_flatten_and_kill(reason=req.reason)
    alert_dispatcher.dispatch("SEV-1", "EMERGENCY KILL SWITCH ENGAGED", req.reason)
    return {
        "status": "HALTED",
        "positions_flattened": closed,
        "message": "Emergency kill executed. All trading halted.",
    }


@app.post("/admin/reset-circuit-breaker")
def reset_circuit_breaker_endpoint(req: ResetCircuitBreakerRequest):
    success = risk_engine.reset_circuit_breaker(token=req.admin_token)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    return {"status": "ACTIVE", "message": "Circuit breaker reset to ACTIVE."}


@app.post("/admin/approve-live")
def approve_live_trading(req: ApproveLiveRequest, db: Session = Depends(get_db)):
    """Required human approval signature for live trading authorization."""
    if len(req.digital_signature) < 16:
        raise HTTPException(status_code=400, detail="Digital signature must be at least 16 characters")

    approval = ApprovalModel(
        approval_id=f"appr_{uuid.uuid4().hex[:8]}",
        action="ENABLE_LIVE_TRADING",
        approved_by=req.approved_by,
        digital_signature=req.digital_signature,
        notes=req.notes,
        approved_at=datetime.now(timezone.utc),
    )
    db.add(approval)
    db.commit()

    alert_dispatcher.dispatch(
        "INFO",
        "Live Trading Human Approval Signed",
        f"Approved by {req.approved_by}. Signature recorded: {req.digital_signature[:8]}...",
    )
    return {
        "approval_id": approval.approval_id,
        "status": "RECORDED",
        "message": "Human approval recorded. Live trading enabled subject to config flags.",
    }
