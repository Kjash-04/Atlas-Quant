"""
Market Data & Snapshot Schemas.
Enforces UTC timestamps, causal indicator fields, and verifiable hash digests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class RegimeLabel(str, Enum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING_LOW_VOL = "RANGING_LOW_VOL"
    RANGING_HIGH_VOL = "RANGING_HIGH_VOL"
    NEWS_SHOCK = "NEWS_SHOCK"
    UNKNOWN = "UNKNOWN"


class NewsEvent(BaseModel):
    time_utc: datetime
    currency: str
    impact: str  # "HIGH", "MEDIUM", "LOW"
    title: str
    minutes_until: float = 0.0

    @field_validator("time_utc")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class IndicatorSet(BaseModel):
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    rsi_14: Optional[float] = None
    atr_14: Optional[float] = None
    atr_percentile_100: Optional[float] = None
    realized_vol_20: Optional[float] = None
    session: str = "OFF_HOURS"  # e.g., "ASIAN", "LONDON", "NEW_YORK", "OVERLAP"
    custom: Dict[str, float] = Field(default_factory=dict)


class AltDataSet(BaseModel):
    vol_index: Optional[float] = None
    funding_rate: Optional[float] = None
    sentiment_score: Optional[float] = None
    additional: Dict[str, Any] = Field(default_factory=dict)


class MarketSnapshot(BaseModel):
    symbol: str
    timestamp_utc: datetime
    timeframe: str  # e.g., "M1", "M5", "M15", "H1"
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float
    indicators: IndicatorSet = Field(default_factory=IndicatorSet)
    news_events: List[NewsEvent] = Field(default_factory=list)
    alt_data: AltDataSet = Field(default_factory=AltDataSet)
    regime_label: RegimeLabel = RegimeLabel.UNKNOWN
    data_hash: str = ""
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("timestamp_utc", "ingested_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    def compute_data_hash(self) -> str:
        """Deterministic sha256 hash of core market values to ensure zero tampering."""
        payload = {
            "symbol": self.symbol,
            "ts": self.timestamp_utc.isoformat(),
            "tf": self.timeframe,
            "o": round(self.open, 6),
            "h": round(self.high, 6),
            "l": round(self.low, 6),
            "c": round(self.close, 6),
            "v": round(self.volume, 4),
            "s": round(self.spread, 4),
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def model_post_init(self, __context: Any) -> None:
        if not self.data_hash:
            self.data_hash = self.compute_data_hash()
