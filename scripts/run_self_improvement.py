"""
Runner Script: Autonomous 7-Step Self-Improvement Loop.
Executes LangGraph state machine from Observe to Store.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.connection import init_db
from src.self_improvement.orchestrator import SelfImprovementOrchestrator
from scripts.generate_sample_data import generate_sample_bars


def main():
    init_db()
    data_path = BASE_DIR / "data" / "sample_bars.csv"
    if not data_path.exists():
        df = generate_sample_bars(2000)
    else:
        df = pd.read_csv(data_path)
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])

    orchestrator = SelfImprovementOrchestrator(data_df=df)
    print("\n=======================================================")
    print("STARTING ATLAS-QUANT 7-STEP SELF-IMPROVEMENT CYCLE")
    print("=======================================================\n")

    final_state = orchestrator.run_cycle()

    print("\n=======================================================")
    print("CYCLE EXECUTION COMPLETED")
    print(f"Cycle ID: {final_state.get('cycle_id')}")
    print(f"Decision: {final_state.get('decision')}")
    print(f"Reason:   {final_state.get('reason')}")
    print(f"Learning ID: {final_state.get('learning_id')}")
    print("\nAudit Event Timeline:")
    for evt in final_state.get("audit_events", []):
        print(f"  • {evt}")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
