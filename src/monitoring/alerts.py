"""
Alert Dispatcher Module.
Dispatches critical operational alerts via Telegram, Slack, and Console.
Enforces zero tolerance for unexpected LLM spend and circuit breaker trips.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(self):
        self.telegram_token = settings.ALERT_TELEGRAM_BOT_TOKEN
        self.telegram_chat_id = settings.ALERT_TELEGRAM_CHAT_ID
        self.slack_webhook = settings.ALERT_SLACK_WEBHOOK_URL
        self.alert_history: List[Dict[str, str]] = []

    def dispatch(self, severity: str, title: str, message: str) -> None:
        """
        severity: "INFO", "WARNING", "CRITICAL", "SEV-1"
        """
        now_str = datetime.now(timezone.utc).isoformat()
        alert_entry = {
            "timestamp": now_str,
            "severity": severity,
            "title": title,
            "message": message,
        }
        self.alert_history.append(alert_entry)

        log_msg = f"[{severity}] {title}: {message}"
        if severity in ("CRITICAL", "SEV-1"):
            logger.critical(log_msg)
        elif severity == "WARNING":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # Telegram webhook
        if self.telegram_token and self.telegram_chat_id:
            try:
                tg_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                payload = {
                    "chat_id": self.telegram_chat_id,
                    "text": f"🚨 Atlas-Quant [{severity}]\n*{title}*\n{message}",
                    "parse_mode": "Markdown",
                }
                httpx.post(tg_url, json=payload, timeout=4.0)
            except Exception as e:
                logger.error(f"Failed to send Telegram alert: {e}")

        # Slack webhook
        if self.slack_webhook:
            try:
                payload = {"text": f":warning: *[Atlas-Quant {severity}] {title}*\n{message}"}
                httpx.post(self.slack_webhook, json=payload, timeout=4.0)
            except Exception as e:
                logger.error(f"Failed to send Slack alert: {e}")

    def alert_budget_exhausted(self, calls_used: int, limit: int) -> None:
        self.dispatch(
            "WARNING",
            "Gemini Deep LLM Budget Exhausted",
            f"Daily call limit reached ({calls_used}/{limit}). Deep reasoning skipped to protect $0 budget cap.",
        )

    def alert_unexpected_cost(self, cost_usd: float) -> None:
        self.dispatch(
            "SEV-1",
            "UNEXPECTED LLM COST DETECTED",
            f"An LLM call recorded an estimated cost of ${cost_usd:.4f}. Immediate investigation required! Zero-spend guarantee breached.",
        )

    def alert_circuit_breaker(self, status: str, reason: str) -> None:
        self.dispatch(
            "CRITICAL",
            f"Circuit Breaker Status Changed to {status}",
            f"Reason: {reason}. Execution engine order submission is blocked.",
        )

    def get_recent_alerts(self, limit: int = 50) -> List[Dict[str, str]]:
        return self.alert_history[-limit:]


alert_dispatcher = AlertDispatcher()
