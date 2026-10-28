"""
Unit Tests: LLM Router & Budget Guard.
Enforces the $0 net spend constraint, daily call limits, and disk caching.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.core.llm_budget import LLMBudgetGuard, BudgetExhaustedError
from src.core.llm_router import LLMRouter


def test_budget_guard_daily_cap():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "test_budget.json"
        guard = LLMBudgetGuard(persistence_file=state_file)
        guard.max_daily_calls = 3

        # First 3 calls succeed
        assert guard.can_call_deep() is True
        guard.record_deep_call(100)
        assert guard.can_call_deep() is True
        guard.record_deep_call(100)
        assert guard.can_call_deep() is True
        guard.record_deep_call(100)

        # 4th call must be blocked
        assert guard.can_call_deep() is False
        with pytest.raises(BudgetExhaustedError):
            guard.record_deep_call(100)

        # Verify estimated spend is 0.00
        status = guard.get_status()
        assert status["estimated_spend_usd"] == 0.00
        assert status["deep_calls_used"] == 3


def test_llm_router_caching_and_free_tier():
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir) / "llm_cache"
        router = LLMRouter(cache_dir=cache_dir)

        prompt = "Evaluate market regime: EURUSD trending bull"
        resp1, rec1 = router.call_routine(prompt, purpose="regime")
        assert rec1.cache_hit is False
        assert rec1.estimated_cost_usd == 0.00

        # Second identical call must be a cache hit
        resp2, rec2 = router.call_routine(prompt, purpose="regime")
        assert rec2.cache_hit is True
        assert resp1 == resp2
        assert rec2.estimated_cost_usd == 0.00


def test_llm_router_deep_call_budget_enforcement():
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir) / "llm_cache"
        router = LLMRouter(cache_dir=cache_dir)
        # Deep call succeeds and records zero cost
        resp, rec = router.call_deep("Diagnose failure in ranging high vol regime", purpose="diagnose")
        assert rec.estimated_cost_usd == 0.00
        assert rec.model_id == router.deep_model
