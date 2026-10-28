"""
Data Ingestion Agent.
Coordinates data validation, gap handling, causal indicator computation, and snapshot distribution.
"""

from __future__ import annotations

import logging
from typing import List, Optional
import pandas as pd
from sqlalchemy.orm import Session

from src.ingestion.adapters import TradingViewWebhookAdapter, MT5Adapter
from src.ingestion.indicators import calculate_indicators, identify_market_regime, detect_session
from src.schemas.market import MarketSnapshot, IndicatorSet, RegimeLabel
from src.database.connection import SessionLocal

logger = logging.getLogger(__name__)


class DataIngestionAgent:
    def __init__(self):
        self.tv_adapter = TradingViewWebhookAdapter()
        self.mt5_adapter = MT5Adapter()

    def process_raw_dataframe(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        db: Optional[Session] = None,
    ) -> List[MarketSnapshot]:
        """
        Cleans raw OHLCV DataFrame, handles gaps, computes causal indicators,
        creates MarketSnapshot records, and persists them.
        """
        if df.empty:
            return []

        # Ensure required columns
        req_cols = {"open", "high", "low", "close", "volume"}
        if not req_cols.issubset(set(df.columns)):
            raise ValueError(f"Missing required columns in DataFrame: {req_cols - set(df.columns)}")

        # Deduplicate and sort chronologically
        if "timestamp_utc" in df.columns:
            df = df.drop_duplicates(subset=["timestamp_utc"]).sort_values("timestamp_utc")
        df = df.reset_index(drop=True)

        # Forward fill small missing gaps in quotes if any
        df = df.ffill().bfill()

        # Compute causal indicators
        df_indicators = calculate_indicators(df)

        snapshots: List[MarketSnapshot] = []
        for _, row in df_indicators.iterrows():
            ts = row.get("timestamp_utc")
            if ts is None:
                continue

            ind = IndicatorSet(
                ema_20=float(row.get("ema_20", row["close"])),
                ema_50=float(row.get("ema_50", row["close"])),
                rsi_14=float(row.get("rsi_14", 50.0)),
                atr_14=float(row.get("atr_14", 0.0015)),
                atr_percentile_100=float(row.get("atr_percentile_100", 50.0)),
                realized_vol_20=float(row.get("realized_vol_20", 0.10)),
                session=str(row.get("session", detect_session(ts))),
            )

            regime = identify_market_regime(
                close=float(row["close"]),
                ema_20=ind.ema_20,
                ema_50=ind.ema_50,
                rsi_14=ind.rsi_14,
                atr_percentile=ind.atr_percentile_100,
            )

            snap = MarketSnapshot(
                symbol=symbol,
                timestamp_utc=ts,
                timeframe=timeframe,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                spread=float(row.get("spread", 0.00015)),
                indicators=ind,
                regime_label=regime,
            )
            self.tv_adapter.persist_and_publish(snap, db=db)
            snapshots.append(snap)

        logger.info(f"DataIngestionAgent processed {len(snapshots)} snapshots for {symbol} ({timeframe}).")
        return snapshots
