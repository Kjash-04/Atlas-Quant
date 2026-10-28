"""
Integration Tests: Autonomous Self-Improvement Loop.
Verifies LangGraph 7-step cycle execution and memory updates.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.self_improvement.orchestrator import SelfImprovementOrchestrator


def test_self_improvement_cycle_run(sample_market_df, db_session):
    orchestrator = SelfImprovementOrchestrator(data_df=sample_market_df)
    final_state = orchestrator.run_cycle()

    assert "cycle_id" in final_state
    assert final_state.get("decision") in ("KEEP", "REVERT")
    assert final_state.get("learning_id") is not None
    assert len(final_state.get("audit_events", [])) >= 5
