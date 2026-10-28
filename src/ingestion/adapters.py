"""
Data Ingestion Adapters.
Ingests from TradingView webhooks, MetaTrader 5, Economic Calendars, and Alt-Data feeds.
Normalizes all inputs into standardized, validated MarketSnapshots.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy.orm import Session

from src.core.event_bus import event_bus
from src.database.connection import SessionLocal
from src.database.models import MarketSnapshotModel
from src.ingestion.indicators import (
    calculate_indicators,
    identify_market_regime,
    detect_session,
)
from src.schemas.market import (
    AltDataSet,
    IndicatorSet,
    MarketSnapshot,
    NewsEvent,
    RegimeLabel,
)

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def ingest(self, raw_data: Any) -> Optional[MarketSnapshot]:
        """Convert raw source data into validated MarketSnapshot."""
        pass

    def persist_and_publish(self, snapshot: MarketSnapshot, db: Optional[Session] = None) -> None:
        """Persist snapshot into database and broadcast on the event bus."""
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            model = MarketSnapshotModel(
                symbol=snapshot.symbol,
                timestamp_utc=snapshot.timestamp_utc,
                timeframe=snapshot.timeframe,
                open=snapshot.open,
                high=snapshot.high,
                low=snapshot.low,
                close=snapshot.close,
                volume=snapshot.volume,
                spread=snapshot.spread,
                indicators_json=snapshot.indicators.model_dump(),
                news_events_json=[e.model_dump(mode="json") for e in snapshot.news_events],
                alt_data_json=snapshot.alt_data.model_dump(),
                regime_label=snapshot.regime_label.value,
                data_hash=snapshot.data_hash,
                ingested_at=snapshot.ingested_at,
            )
            db.add(model)
            db.commit()
            # Publish event
            event_bus.publish(f"market.snapshot.{snapshot.symbol}", snapshot)
            logger.debug(f"Persisted & published snapshot for {snapshot.symbol} @ {snapshot.timestamp_utc}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist snapshot: {e}")
        finally:
            if own_session:
                db.close()


class TradingViewWebhookAdapter(BaseAdapter):
    def __init__(self):
        super().__init__("TradingViewWebhook")

    def ingest(self, raw_payload: Dict[str, Any]) -> Optional[MarketSnapshot]:
        """
        Parses incoming JSON webhook from TradingView alert:
        {
          "symbol": "EURUSD",
          "timestamp": "2026-10-26T12:00:00Z",
          "timeframe": "M15",
          "open": 1.0850, "high": 1.0870, "low": 1.0845, "close": 1.0865,
          "volume": 1420.0, "spread": 0.00012,
          "news": [...], "alt_data": {...}
        }
        """
        try:
            ts = raw_payload.get("timestamp")
            if isinstance(ts, str):
                ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, (int, float)):
                ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                ts_dt = datetime.now(timezone.utc)

            symbol = raw_payload.get("symbol", "EURUSD").upper()
            close_val = float(raw_payload["close"])
            open_val = float(raw_payload.get("open", close_val))
            high_val = float(raw_payload.get("high", max(open_val, close_val)))
            low_val = float(raw_payload.get("low", min(open_val, close_val)))
            vol = float(raw_payload.get("volume", 100.0))
            spread = float(raw_payload.get("spread", 0.00015))

            # Indicators passed or placeholder
            ind_dict = raw_payload.get("indicators", {})
            indicators = IndicatorSet(
                ema_20=ind_dict.get("ema_20", close_val),
                ema_50=ind_dict.get("ema_50", close_val),
                rsi_14=ind_dict.get("rsi_14", 50.0),
                atr_14=ind_dict.get("atr_14", 0.0015),
                atr_percentile_100=ind_dict.get("atr_percentile_100", 50.0),
                realized_vol_20=ind_dict.get("realized_vol_20", 0.12),
                session=detect_session(ts_dt),
            )

            # News
            news_items = []
            for n in raw_payload.get("news", []):
                news_items.append(
                    NewsEvent(
                        time_utc=datetime.fromisoformat(n["time_utc"]),
                        currency=n["currency"],
                        impact=n["impact"],
                        title=n["title"],
                        minutes_until=float(n.get("minutes_until", 0.0)),
                    )
                )

            # Alt data
            alt_dict = raw_payload.get("alt_data", {})
            alt_data = AltDataSet(
                vol_index=alt_dict.get("vol_index"),
                funding_rate=alt_dict.get("funding_rate"),
                sentiment_score=alt_dict.get("sentiment_score"),
            )

            regime = identify_market_regime(
                close=close_val,
                ema_20=indicators.ema_20 or close_val,
                ema_50=indicators.ema_50 or close_val,
                rsi_14=indicators.rsi_14 or 50.0,
                atr_percentile=indicators.atr_percentile_100 or 50.0,
                has_imminent_high_impact_news=any(n.impact == "HIGH" and n.minutes_until <= 30 for n in news_items),
            )

            snapshot = MarketSnapshot(
                symbol=symbol,
                timestamp_utc=ts_dt,
                timeframe=raw_payload.get("timeframe", "M15"),
                open=open_val,
                high=high_val,
                low=low_val,
                close=close_val,
                volume=vol,
                spread=spread,
                indicators=indicators,
                news_events=news_items,
                alt_data=alt_data,
                regime_label=regime,
            )
            self.persist_and_publish(snapshot)
            return snapshot
        except Exception as e:
            logger.error(f"TradingView webhook ingestion error: {e}")
            return None


class MT5Adapter(BaseAdapter):
    def __init__(self):
        super().__init__("MetaTrader5Ingestion")

    def ingest(self, raw_ticks_or_rates: Any) -> Optional[MarketSnapshot]:
        """
        Transforms MetaTrader 5 rate dict or numpy record into MarketSnapshot.
        """
        try:
            if isinstance(raw_ticks_or_rates, dict):
                d = raw_ticks_or_rates
                ts = datetime.fromtimestamp(d.get("time", datetime.now().timestamp()), tz=timezone.utc)
                close_val = float(d.get("close", d.get("bid", 1.0850)))
                open_val = float(d.get("open", close_val))
                high_val = float(d.get("high", close_val))
                low_val = float(d.get("low", close_val))
                vol = float(d.get("tick_volume", d.get("volume", 50.0)))
                spread = float(d.get("spread", 0.00015))
                symbol = d.get("symbol", "EURUSD")
                timeframe = d.get("timeframe", "M15")
            else:
                return None

            indicators = IndicatorSet(
                ema_20=close_val,
                ema_50=close_val,
                rsi_14=50.0,
                atr_14=0.0015,
                atr_percentile_100=50.0,
                realized_vol_20=0.10,
                session=detect_session(ts),
            )

            snapshot = MarketSnapshot(
                symbol=symbol,
                timestamp_utc=ts,
                timeframe=timeframe,
                open=open_val,
                high=high_val,
                low=low_val,
                close=close_val,
                volume=vol,
                spread=spread,
                indicators=indicators,
                regime_label=RegimeLabel.RANGING_LOW_VOL,
            )
            self.persist_and_publish(snapshot)
            return snapshot
        except Exception as e:
            logger.error(f"MT5 ingestion adapter error: {e}")
            return None


class NewsCalendarAdapter(BaseAdapter):
    def __init__(self):
        super().__init__("NewsCalendar")

    def ingest(self, raw_events: List[Dict[str, Any]]) -> List[NewsEvent]:
        events = []
        now_utc = datetime.now(timezone.utc)
        for ev in raw_events:
            ev_time = datetime.fromisoformat(ev["time_utc"].replace("Z", "+00:00"))
            mins_until = (ev_time - now_utc).total_seconds() / 60.0
            events.append(
                NewsEvent(
                    time_utc=ev_time,
                    currency=ev.get("currency", "USD"),
                    impact=ev.get("impact", "HIGH"),
                    title=ev.get("title", "Economic Event"),
                    minutes_until=max(0.0, mins_until),
                )
            )
        return events


class AlternativeDataAdapter(BaseAdapter):
    def __init__(self):
        super().__init__("AlternativeData")

    def ingest(self, raw_data: Dict[str, Any]) -> AltDataSet:
        return AltDataSet(
            vol_index=raw_data.get("vol_index", 18.5),
            funding_rate=raw_data.get("funding_rate", 0.0001),
            sentiment_score=raw_data.get("sentiment_score", 0.52),
            additional=raw_data.get("metadata", {}),
        )
