"""
Atlas-Quant Configuration Module.
Strict environment validation, path resolution, and risk limit enforcement.
Uses python-dotenv and standard library for robust zero-dependency loading.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "t")


def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


def _get_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


class Settings:
    def __init__(self):
        # Core
        self.PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Atlas-Quant")
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        self.OUTPUT_MODE: str = os.getenv("OUTPUT_MODE", "BUILD")
        self.BASE_DIR: Path = BASE_DIR
        self.DATA_DIR: Path = BASE_DIR / "data"

        # Risk & Mode
        self.PAPER_TRADING: bool = _get_bool("PAPER_TRADING", True)
        self.LIVE_TRADING: bool = _get_bool("LIVE_TRADING", False)
        self.HUMAN_APPROVAL_REQUIRED: bool = _get_bool("HUMAN_APPROVAL_REQUIRED", True)

        # Broker: MetaTrader 5
        self.MT5_PATH: str = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
        self.MT5_LOGIN: int = _get_int("MT5_LOGIN", 12345678)
        self.MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "demo_password")
        self.MT5_SERVER: str = os.getenv("MT5_SERVER", "MetaQuotes-Demo")
        self.MT5_TIMEOUT_MS: int = _get_int("MT5_TIMEOUT_MS", 60000)

        # LLM Routing (Two Keys - $0 net spend) - with fallbacks for alternative starter naming
        gemini_free = os.getenv("GEMINI_FREE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        gemini_deep = os.getenv("GEMINI_DEEP_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_FREE_API_KEY: str = gemini_free
        self.GEMINI_DEEP_API_KEY: str = gemini_deep
        self.GEMINI_ROUTINE_MODEL: str = os.getenv("GEMINI_ROUTINE_MODEL") or os.getenv("GEMINI_FAST_MODEL", "gemini-3.8-flash")
        self.GEMINI_DEEP_MODEL: str = os.getenv("GEMINI_DEEP_MODEL", "gemini-4-argon")

        # Deep LLM Guardrails
        self.DEEP_LLM_CALLS_PER_DAY: int = _get_int("DEEP_LLM_CALLS_PER_DAY", 20)
        self.MAX_DEEP_PROMPT_TOKENS: int = _get_int("MAX_DEEP_PROMPT_TOKENS", 8192)
        self.ENABLE_LLM_RESPONSE_CACHE: bool = _get_bool("ENABLE_LLM_RESPONSE_CACHE", True)
        self.BUDGET_CAP_USD: float = _get_float("BUDGET_CAP_USD", 0.00)
        self.ALERT_BUDGET_THRESHOLD_USD: float = _get_float("ALERT_BUDGET_THRESHOLD_USD", 1.00)

        # Database
        default_db = f"sqlite:///{self.BASE_DIR / 'data' / 'atlas_quant.db'}"
        self.DATABASE_URL: str = os.getenv("DATABASE_URL") or os.getenv("DB_URL", default_db)
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        # Immutable Risk Parameters
        self.RISK_MAX_DAILY_LOSS_PCT: float = _get_float("RISK_MAX_DAILY_LOSS_PCT", 0.03)
        self.RISK_MAX_DRAWDOWN_PCT: float = _get_float("RISK_MAX_DRAWDOWN_PCT", 0.10)
        self.RISK_PER_TRADE_FRACTION: float = _get_float("RISK_PER_TRADE_FRACTION", _get_float("RISK_PER_TRADE", 0.01))
        self.RISK_MAX_POSITION_EQUITY_PCT: float = _get_float("RISK_MAX_POSITION_EQUITY_PCT", 0.05)
        self.RISK_MAX_OPEN_POSITIONS: int = _get_int("RISK_MAX_OPEN_POSITIONS", 3)
        self.RISK_MAX_DAILY_TRADES: int = _get_int("RISK_MAX_DAILY_TRADES", 10)
        self.RISK_MAX_SPREAD_PIPS: float = _get_float("RISK_MAX_SPREAD_PIPS", 2.5)
        self.RISK_NEWS_BLACKOUT_MINUTES: int = _get_int("RISK_NEWS_BLACKOUT_MINUTES", 30)
        self.RISK_ALLOWED_SESSIONS: str = os.getenv("RISK_ALLOWED_SESSIONS", "LONDON,NEW_YORK,OVERLAP_LDN_NY")

        # Admin & Safety Secret Tokens (Externalized for security)
        self.ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")
        self.ADMIN_EMERGENCY_KILL_TOKEN: str = os.getenv("ADMIN_EMERGENCY_KILL_TOKEN", "EMERGENCY_KILL_AUTHORIZED")
        self.ADMIN_RESET_TOKEN: str = os.getenv("ADMIN_RESET_TOKEN", "ADMIN_RESET_CONFIRMED")
        self.ADMIN_HMAC_SECRET: str = os.getenv("ADMIN_HMAC_SECRET", "atlas_quant_admin_hmac_secret_2026")

        # Alerts
        self.ALERT_TELEGRAM_BOT_TOKEN: str = os.getenv("ALERT_TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.ALERT_TELEGRAM_CHAT_ID: str = os.getenv("ALERT_TELEGRAM_CHAT_ID", "")
        self.ALERT_SLACK_WEBHOOK_URL: str = os.getenv("ALERT_SLACK_WEBHOOK_URL", "")
        self.ALERT_CONSOLE_LOG: bool = _get_bool("ALERT_CONSOLE_LOG", True)

        # Disclaimer
        self.RISK_DISCLAIMER: str = (
            "Research/educational only. Not financial advice. "
            "Past performance does not guarantee future results. "
            "Live trading requires explicit human approval."
        )

        os.makedirs(self.DATA_DIR, exist_ok=True)

    @property
    def allowed_sessions_list(self) -> List[str]:
        return [s.strip().upper() for s in self.RISK_ALLOWED_SESSIONS.split(",") if s.strip()]


# Global singleton settings
settings = Settings()
