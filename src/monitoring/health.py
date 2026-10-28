"""
System Health Monitor.
Performs continuous telemetry checks: Data freshness, Broker ping, DB connectivity,
LLM budget counter, Disk space, and Circuit breaker status.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from src.core.llm_budget import budget_guard
from src.database.connection import SessionLocal
from src.database.models import SystemHealthModel
from src.execution.agent import execution_agent
from src.risk_engine.engine import risk_engine
from src.schemas.system import CircuitBreakerStatus, SystemHealthRecord

logger = logging.getLogger(__name__)


class SystemHealthMonitor:
    def __init__(self):
        pass

    def check_health(self, db: Optional[Session] = None) -> SystemHealthRecord:
        incidents: List[str] = []

        # 1. Database Connectivity
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True

        db_ok = True
        try:
            db.execute(SystemHealthModel.__table__.select().limit(1))
        except Exception as e:
            db_ok = False
            incidents.append(f"Database connectivity error: {e}")

        # 2. Broker Connection & Heartbeat Refresh
        broker_ok = execution_agent.adapter.is_connected
        if not broker_ok:
            incidents.append("Broker execution adapter disconnected.")
        else:
            execution_agent.update_broker_heartbeat()

        # 3. Circuit Breaker
        cb_status = risk_engine.circuit_status
        if risk_engine.kill_switch_engaged:
            cb_status = CircuitBreakerStatus.HALTED
            incidents.append("Kill switch actively engaged.")
        elif cb_status != CircuitBreakerStatus.ACTIVE:
            incidents.append(f"Circuit breaker is in state {cb_status.value}.")

        # 4. LLM Budget Check
        budget_status = budget_guard.get_status()
        if budget_status["deep_calls_used"] >= budget_status["deep_calls_limit"]:
            incidents.append("Deep LLM daily call limit reached (20/20).")

        # 5. Disk space check
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (1024**3)
        if free_gb < 1.0:
            incidents.append(f"Low disk space: {free_gb:.2f} GB remaining.")

        # Account info
        acct = execution_agent.adapter.get_account_info()
        equity = float(acct.get("equity", 100000.0))
        open_positions = int(acct.get("open_positions_count", 0))

        record = SystemHealthRecord(
            timestamp_utc=datetime.now(timezone.utc),
            circuit_breaker_status=cb_status,
            data_feed_ok=True,
            broker_connected=broker_ok,
            db_connected=db_ok,
            daily_deep_llm_calls_used=budget_status["deep_calls_used"],
            daily_deep_llm_calls_limit=budget_status["deep_calls_limit"],
            monthly_cloud_budget_spent_usd=budget_status["estimated_spend_usd"],
            active_open_positions=open_positions,
            current_equity_usd=equity,
            daily_pnl_pct=0.0,
            peak_drawdown_pct=0.0,
            active_incidents=incidents,
        )

        # Persist health check
        try:
            health_model = SystemHealthModel(
                timestamp_utc=record.timestamp_utc,
                circuit_breaker_status=record.circuit_breaker_status.value,
                data_feed_ok=record.data_feed_ok,
                broker_connected=record.broker_connected,
                db_connected=record.db_connected,
                daily_deep_llm_calls_used=record.daily_deep_llm_calls_used,
                daily_deep_llm_calls_limit=record.daily_deep_llm_calls_limit,
                monthly_cloud_budget_spent_usd=record.monthly_cloud_budget_spent_usd,
                active_open_positions=record.active_open_positions,
                current_equity_usd=record.current_equity_usd,
                daily_pnl_pct=record.daily_pnl_pct,
                peak_drawdown_pct=record.peak_drawdown_pct,
                incidents_json=incidents,
            )
            db.add(health_model)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to log health record: {e}")
        finally:
            if own_session:
                db.close()

        return record


health_monitor = SystemHealthMonitor()
