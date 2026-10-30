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
    filled_count = 0
    expected_rejections: list[tuple[int, str, str]] = []
    unexpected_rejections: list[tuple[int, str, str]] = []

    for i in range(iterations):
        execution_agent.update_broker_heartbeat()
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

        # Tick open positions against market price bounds
        closed_positions = execution_agent.tick_open_positions(snap)
        for cp in closed_positions:
            print(f"  -> Position #{cp['ticket']} Closed: PnL ${cp['pnl_usd']:+.2f} ({cp['pnl_pips']:+.1f} pips) via {cp['exit_reason']}")

        # Submit simulated order intent with side-aware brackets
        side = OrderSide.BUY if i % 2 == 0 else OrderSide.SELL
        if side == OrderSide.BUY:
            sl_price = snap.close - 0.0015
            tp_price = snap.close + 0.0030
        else:
            sl_price = snap.close + 0.0015
            tp_price = snap.close - 0.0030

        intent = OrderIntent(
            intent_id=f"intent_{uuid.uuid4().hex[:8]}",
            strategy_id="strat_ema_rsi_trend",
            version_id="v1.0.0",
            symbol="EURUSD",
            side=side,
            requested_lots=0.10,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            idempotency_key=f"idemp_{uuid.uuid4().hex[:8]}",
        )

        res = execution_agent.process_order_intent(intent, snapshot=snap)
        print(f"  -> Order Execution Status: {res.status} (Lots: {res.executed_lots}, Fill: {res.executed_price})")
        if res.error_message:
            print(f"     Note: {res.error_message}")

        if res.status == "FILLED":
            filled_count += 1
        else:
            err = res.error_message or ""
            expected_keywords = ["open positions", "daily trade", "limit", "cap", "position"]
            if any(kw in err.lower() for kw in expected_keywords):
                expected_rejections.append((i + 1, side.value, err))
            else:
                unexpected_rejections.append((i + 1, side.value, err))

        health = health_monitor.check_health()
        print(f"  -> System Health: Circuit={health.circuit_breaker_status.value}, Deep LLM Used={health.daily_deep_llm_calls_used}/20\n")
        time.sleep(0.5)

    print("=======================================================")
    print(f"SOAK SUMMARY: {filled_count}/{iterations} filled, {len(expected_rejections)}/{iterations} risk-gated\n")

    if expected_rejections:
        print("Expected risk-gate rejections (position/trade caps working correctly):")
        for iter_num, side_val, err_msg in expected_rejections:
            print(f"  [{iter_num}/{iterations}] {side_val}: {err_msg}")
        print()

    if unexpected_rejections:
        print("UNEXPECTED REJECTIONS:")
        for iter_num, side_val, err_msg in unexpected_rejections:
            print(f"  [{iter_num}/{iterations}] {side_val}: {err_msg}")
        print("\nSOAK TEST FAILED")
        print("=======================================================\n")
        sys.exit(1)

    print(f"SOAK TEST COMPLETED SUCCESSFULLY: {filled_count} filled, {len(expected_rejections)} correctly risk-gated.")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
