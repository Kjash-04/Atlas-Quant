"""
Runner Script: Paper Trading Soak Test Harness.
Simulates a live monitoring loop feeding ticks/bars, gating with RiskEngine, and executing paper orders.
"""

from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.connection import init_db
from src.execution.agent import execution_agent
from src.ingestion.adapters import TradingViewWebhookAdapter
from src.monitoring.health import health_monitor
from src.schemas.trade import OrderIntent, OrderSide
from scripts.generate_sample_data import generate_sample_bars


def main():
    init_db()
    data_path = BASE_DIR / "data" / "sample_bars.csv"
    if not data_path.exists():
        df = generate_sample_bars(500)
    else:
        df = pd.read_csv(data_path).tail(200)

    adapter = TradingViewWebhookAdapter()

    print("\n=======================================================")
    print("STARTING PAPER TRADING SOAK TEST HARNESS")
    print("Strict RiskEngine pre-trade gates & $0 spend enforcement")
    print("=======================================================\n")

    iterations = 5
    for i in range(iterations):
        row = df.iloc[i]
        payload = {
            "symbol": "EURUSD",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timeframe": "M15",
            "close": float(row["close"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": float(row["volume"]),
            "spread": 0.00015,
        }
        snap = adapter.ingest(payload)
        print(f"[{i+1}/{iterations}] Ingested Snapshot: {snap.symbol} @ {snap.close} (Regime: {snap.regime_label.value})")

        # Submit simulated order intent
        intent = OrderIntent(
            intent_id=f"intent_{uuid.uuid4().hex[:8]}",
            strategy_id="strat_ema_rsi_trend",
            version_id="v1.0.0",
            symbol="EURUSD",
            side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
            requested_lots=0.10,
            stop_loss_price=snap.close - 0.0015,
            take_profit_price=snap.close + 0.0030,
            idempotency_key=f"idemp_{uuid.uuid4().hex[:8]}",
        )

        res = execution_agent.process_order_intent(intent, snapshot=snap)
        print(f"  -> Order Execution Status: {res.status} (Lots: {res.executed_lots}, Fill: {res.executed_price})")
        if res.error_message:
            print(f"     Note: {res.error_message}")

        health = health_monitor.check_health()
        print(f"  -> System Health: Circuit={health.circuit_breaker_status.value}, Deep LLM Used={health.daily_deep_llm_calls_used}/20\n")
        time.sleep(0.5)

    print("=======================================================")
    print("SOAK TEST ITERATIONS COMPLETED SUCCESSFULLY")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
