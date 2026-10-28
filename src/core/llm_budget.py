"""
LLM Budget Guard & Hard Daily Counter.
Enforces the $0 net spend constraint and strict 20 calls/day cap for Gemini 4 Argon.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from src.config import settings

logger = logging.getLogger(__name__)


class BudgetExhaustedError(Exception):
    """Raised when deep model daily calls exceed limit or budget cap is breached."""
    pass


class LLMBudgetGuard:
    def __init__(self, persistence_file: Path | None = None):
        self.persistence_file = persistence_file or (settings.DATA_DIR / "llm_budget_state.json")
        self.max_daily_calls = settings.DEEP_LLM_CALLS_PER_DAY
        self.budget_cap_usd = settings.BUDGET_CAP_USD
        self._load_state()

    def _load_state(self) -> None:
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.persistence_file.exists():
            try:
                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == today_utc:
                    self.current_date = today_utc
                    self.deep_calls_today = data.get("deep_calls_today", 0)
                    self.total_tokens_today = data.get("total_tokens_today", 0)
                    self.estimated_spend_usd = data.get("estimated_spend_usd", 0.0)
                    return
            except Exception as e:
                logger.warning(f"Failed to read budget state file, resetting: {e}")

        # Default / New Day Reset
        self.current_date = today_utc
        self.deep_calls_today = 0
        self.total_tokens_today = 0
        self.estimated_spend_usd = 0.0
        self._save_state()

    def _save_state(self) -> None:
        self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "date": self.current_date,
            "deep_calls_today": self.deep_calls_today,
            "total_tokens_today": self.total_tokens_today,
            "estimated_spend_usd": self.estimated_spend_usd,
            "max_daily_calls": self.max_daily_calls,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.persistence_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def rollover_check(self) -> None:
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.current_date != today_utc:
            self._load_state()

    def can_call_deep(self) -> bool:
        """Checks if a Gemini 4 Argon deep call is permitted."""
        self.rollover_check()
        if self.deep_calls_today >= self.max_daily_calls:
            logger.warning(f"LLM Budget Guard: daily limit reached ({self.deep_calls_today}/{self.max_daily_calls}).")
            return False
        if self.estimated_spend_usd > self.budget_cap_usd:
            logger.critical(f"LLM Budget Guard: Spend cap ${self.budget_cap_usd} exceeded!")
            return False
        return True

    def record_deep_call(self, tokens_used: int = 0) -> None:
        """Records an authorized deep call and updates daily counter."""
        self.rollover_check()
        if self.deep_calls_today >= self.max_daily_calls:
            raise BudgetExhaustedError(
                f"BUDGET_EXHAUSTED: Cannot execute deep Gemini 4 Argon call. "
                f"Daily limit ({self.max_daily_calls}) reached for {self.current_date}."
            )
        self.deep_calls_today += 1
        self.total_tokens_today += tokens_used
        # Monthly Google AI Pro cloud credit covers calls -> net spend is 0.00
        self.estimated_spend_usd = 0.00
        self._save_state()
        logger.info(f"Recorded Deep LLM Call: {self.deep_calls_today}/{self.max_daily_calls} used today.")

    def get_status(self) -> Dict[str, Any]:
        self.rollover_check()
        return {
            "date": self.current_date,
            "deep_calls_used": self.deep_calls_today,
            "deep_calls_limit": self.max_daily_calls,
            "remaining_deep_calls": max(0, self.max_daily_calls - self.deep_calls_today),
            "estimated_spend_usd": self.estimated_spend_usd,
            "budget_cap_usd": self.budget_cap_usd,
            "overages_allowed": False
        }


budget_guard = LLMBudgetGuard()
