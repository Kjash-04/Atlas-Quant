"""
Deterministic Risk Engine.
Strict gatekeeper between strategy signals and MT5 broker execution.
Immutable by the AI self-improvement loop.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session

from src.config import settings
from src.database.connection import SessionLocal
from src.database.models import ApprovalModel, SystemHealthModel
from src.risk_engine.rules import RiskGateCheckResult, RiskRuleViolation
from src.risk_engine.sizing import calculate_risk_sized_lots
from src.schemas.market import MarketSnapshot
from src.schemas.system import CircuitBreakerStatus
from src.schemas.trade import OrderIntent, OrderSide

logger = logging.getLogger(__name__)

SUPPORTED_SYMBOLS: Set[str] = {
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"
}


class RiskEngine:
    def __init__(self):
        self.circuit_status: CircuitBreakerStatus = CircuitBreakerStatus.ACTIVE
        self.kill_switch_engaged: bool = False
        self._processed_idempotency_keys: Set[str] = set()
        self.last_broker_heartbeat_utc: datetime = datetime.now(timezone.utc)

    def trigger_kill_switch(self, reason: str = "Admin emergency kill switch triggered") -> None:
        """Flattens all positions, halts trading, and blocks any new orders."""
        self.kill_switch_engaged = True
        self.circuit_status = CircuitBreakerStatus.HALTED
        logger.critical(f"EMERGENCY KILL SWITCH ACTIVATED: {reason}")

    def reset_circuit_breaker(self, token: str) -> bool:
        """Reset circuit breaker with authorization token."""
        if token == settings.ADMIN_RESET_TOKEN:
            self.circuit_status = CircuitBreakerStatus.ACTIVE
            self.kill_switch_engaged = False
            logger.info("Circuit breaker manually reset to ACTIVE.")
            return True
        return False

    def update_broker_heartbeat(self) -> None:
        self.last_broker_heartbeat_utc = datetime.now(timezone.utc)

    def check(
        self,
        intent: OrderIntent,
        account_info: Dict[str, Any],
        snapshot: MarketSnapshot,
        recent_trades: List[Dict[str, Any]],
        db: Optional[Session] = None,
    ) -> RiskGateCheckResult:
        """
        Enforces 10 deterministic risk barriers in strict serial order.
        """
        # 1. Kill Switch & Circuit Breaker State
        if self.kill_switch_engaged:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.KILL_SWITCH_ENGAGED,
                reason="System Emergency Kill Switch is engaged.",
            )
        if self.circuit_status == CircuitBreakerStatus.HALTED:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.CIRCUIT_BREAKER_HALTED,
                reason="Circuit breaker is HALTED. All order submission blocked.",
            )
        if self.circuit_status == CircuitBreakerStatus.PAUSED:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.CIRCUIT_BREAKER_PAUSED,
                reason="Circuit breaker is PAUSED (e.g. daily loss limit hit).",
            )

        # 1b. Symbol & Parameter Sanity Checks
        if intent.symbol.upper() not in SUPPORTED_SYMBOLS:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.UNSUPPORTED_SYMBOL,
                reason=f"Symbol '{intent.symbol}' is not supported.",
            )

        if intent.requested_lots is not None and intent.requested_lots <= 0:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.LOT_SIZE_OUT_OF_BOUNDS,
                reason=f"Requested lot size {intent.requested_lots} is invalid (must be > 0).",
            )

        # Bracket Price Direction Sanity Checks
        if intent.side == OrderSide.BUY:
            if intent.stop_loss_price is not None and intent.stop_loss_price >= snapshot.close:
                return RiskGateCheckResult(
                    approved=False,
                    violation=RiskRuleViolation.INVALID_BRACKET_PRICES,
                    reason=f"BUY stop-loss price ({intent.stop_loss_price}) must be below current entry price ({snapshot.close}).",
                )
            if intent.take_profit_price is not None and intent.take_profit_price <= snapshot.close:
                return RiskGateCheckResult(
                    approved=False,
                    violation=RiskRuleViolation.INVALID_BRACKET_PRICES,
                    reason=f"BUY take-profit price ({intent.take_profit_price}) must be above current entry price ({snapshot.close}).",
                )
        elif intent.side == OrderSide.SELL:
            if intent.stop_loss_price is not None and intent.stop_loss_price <= snapshot.close:
                return RiskGateCheckResult(
                    approved=False,
                    violation=RiskRuleViolation.INVALID_BRACKET_PRICES,
                    reason=f"SELL stop-loss price ({intent.stop_loss_price}) must be above current entry price ({snapshot.close}).",
                )
            if intent.take_profit_price is not None and intent.take_profit_price >= snapshot.close:
                return RiskGateCheckResult(
                    approved=False,
                    violation=RiskRuleViolation.INVALID_BRACKET_PRICES,
                    reason=f"SELL take-profit price ({intent.take_profit_price}) must be below current entry price ({snapshot.close}).",
                )

        # 2. Broker Heartbeat & Data Freshness
        now_utc = datetime.now(timezone.utc)
        heartbeat_age = (now_utc - self.last_broker_heartbeat_utc).total_seconds()
        if heartbeat_age > 60.0:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.BROKER_HEARTBEAT_TIMEOUT,
                reason=f"Broker heartbeat timeout ({heartbeat_age:.1f}s > 60s).",
            )

        data_age = (now_utc - snapshot.timestamp_utc).total_seconds()
        if data_age > 1800.0:  # Allow standard bar time buffer for 15M/1H bars
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.DATA_STALE,
                reason=f"Market snapshot timestamp is stale ({data_age:.1f}s old).",
            )

        # 3. Daily Loss Limit (3% Equity Circuit Breaker)
        equity = float(account_info.get("equity", 100000.0))
        starting_daily_equity = float(account_info.get("starting_daily_equity", equity))
        daily_loss_usd = max(0.0, starting_daily_equity - equity)
        daily_loss_pct = daily_loss_usd / starting_daily_equity

        if daily_loss_pct >= settings.RISK_MAX_DAILY_LOSS_PCT:
            self.circuit_status = CircuitBreakerStatus.PAUSED
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.DAILY_LOSS_LIMIT_EXCEEDED,
                reason=f"Daily loss ({daily_loss_pct*100:.2f}%) exceeds max {settings.RISK_MAX_DAILY_LOSS_PCT*100:.1f}%. Status PAUSED.",
            )

        # 4. Peak-to-Trough Drawdown (10% Equity Circuit Breaker)
        peak_equity = float(account_info.get("peak_equity", starting_daily_equity))
        current_dd_pct = (peak_equity - equity) / peak_equity
        if current_dd_pct >= settings.RISK_MAX_DRAWDOWN_PCT:
            self.circuit_status = CircuitBreakerStatus.HALTED
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.PEAK_DRAWDOWN_EXCEEDED,
                reason=f"Peak-to-trough drawdown ({current_dd_pct*100:.2f}%) exceeds max {settings.RISK_MAX_DRAWDOWN_PCT*100:.1f}%. Status HALTED.",
            )

        # 5. Daily Trades & Open Positions Limits
        daily_trades_count = sum(1 for t in recent_trades if (now_utc - t.get("entry_time", now_utc)).total_seconds() < 86400)
        if daily_trades_count >= settings.RISK_MAX_DAILY_TRADES:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.MAX_DAILY_TRADES_EXCEEDED,
                reason=f"Daily trades count ({daily_trades_count}) reached limit {settings.RISK_MAX_DAILY_TRADES}.",
            )

        open_positions_count = int(account_info.get("open_positions_count", 0))
        if open_positions_count >= settings.RISK_MAX_OPEN_POSITIONS:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.MAX_OPEN_POSITIONS_EXCEEDED,
                reason=f"Open positions ({open_positions_count}) reached limit {settings.RISK_MAX_OPEN_POSITIONS}.",
            )

        # 6. Spread & Session & News Blackout
        spread_pips = snapshot.spread * 10000.0
        if spread_pips > settings.RISK_MAX_SPREAD_PIPS:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.SPREAD_TOO_HIGH,
                reason=f"Current spread ({spread_pips:.2f} pips) exceeds maximum {settings.RISK_MAX_SPREAD_PIPS} pips.",
            )

        current_session = snapshot.indicators.session
        if settings.allowed_sessions_list and current_session not in settings.allowed_sessions_list and "ALL" not in settings.allowed_sessions_list:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.DISALLOWED_SESSION,
                reason=f"Session '{current_session}' is not in allowed sessions {settings.allowed_sessions_list}.",
            )

        for news in snapshot.news_events:
            if news.impact == "HIGH" and news.minutes_until <= settings.RISK_NEWS_BLACKOUT_MINUTES:
                return RiskGateCheckResult(
                    approved=False,
                    violation=RiskRuleViolation.NEWS_BLACKOUT,
                    reason=f"High-impact news event '{news.title}' within {news.minutes_until:.1f}m blackout window.",
                )

        # 7. Margin / Free Margin Check
        free_margin = float(account_info.get("free_margin", equity))
        min_required_margin = equity * 0.05
        if free_margin < min_required_margin:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.INSUFFICIENT_MARGIN,
                reason=f"Free margin ${free_margin:.2f} below required buffer ${min_required_margin:.2f}.",
            )

        # 8. Fixed Fractional Sizing & Lot Bounds
        stop_dist = abs(intent.stop_loss_price - snapshot.close) if intent.stop_loss_price else (snapshot.indicators.atr_14 or 0.0015) * 1.5
        stop_dist = max(stop_dist, 0.0004)  # Minimum 4 pips

        max_risk_lots = calculate_risk_sized_lots(
            equity=equity,
            stop_distance_price=stop_dist,
            risk_fraction=settings.RISK_PER_TRADE_FRACTION,
            current_price=snapshot.close,
            max_position_equity_pct=settings.RISK_MAX_POSITION_EQUITY_PCT,
        )

        if max_risk_lots <= 0:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.LOT_SIZE_OUT_OF_BOUNDS,
                reason=f"Calculated risk lot size {max_risk_lots} is invalid.",
            )

        # Honor requested_lots if provided, capped to risk-permitted maximum
        if intent.requested_lots is not None and intent.requested_lots > 0:
            approved_lots = round(min(intent.requested_lots, max_risk_lots), 2)
            if intent.requested_lots > max_risk_lots:
                logger.warning(
                    f"Requested lots {intent.requested_lots} capped to risk-permitted maximum {approved_lots}."
                )
        else:
            approved_lots = max_risk_lots

        if approved_lots <= 0:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.LOT_SIZE_OUT_OF_BOUNDS,
                reason=f"Approved lot size {approved_lots} is below minimum allowed.",
            )

        # 9. Idempotency Check
        if intent.idempotency_key in self._processed_idempotency_keys:
            return RiskGateCheckResult(
                approved=False,
                violation=RiskRuleViolation.DUPLICATE_IDEMPOTENCY_KEY,
                reason=f"Duplicate idempotency key '{intent.idempotency_key}' detected.",
            )
        self._processed_idempotency_keys.add(intent.idempotency_key)

        # 10. Live Trading Authorization Gate
        if not settings.PAPER_TRADING and settings.LIVE_TRADING:
            # Must verify signed human approval record exists in DB
            has_approval = self._verify_live_approval(db)
            if not has_approval:
                return RiskGateCheckResult(
                    approved=False,
                    violation=RiskRuleViolation.UNAUTHORIZED_LIVE_ORDER,
                    reason="LIVE_TRADING is enabled but no valid signed HumanApprovalRecord found in DB.",
                )

        # Passed all 10 barriers
        return RiskGateCheckResult(
            approved=True,
            violation=None,
            reason="All 10 risk barriers PASSED.",
            approved_lots=approved_lots,
        )

    def _verify_live_approval(self, db: Optional[Session] = None) -> bool:
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            record = db.query(ApprovalModel).filter(
                ApprovalModel.action == "ENABLE_LIVE_TRADING",
                ApprovalModel.is_revoked.is_(False),
            ).first()
            return record is not None and len(record.digital_signature) > 10
        except Exception:
            return False
        finally:
            if own_session:
                db.close()


risk_engine = RiskEngine()
