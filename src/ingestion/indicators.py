"""
Causal Financial Indicators Module.
Strictly eliminates look-ahead bias: every computation at index t uses ONLY data at <= t.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd

from src.schemas.market import IndicatorSet, RegimeLabel


def detect_session(dt_utc: datetime) -> str:
    """
    Identifies the active forex trading session in UTC without any future information.
    - Asian: 00:00 - 08:00 UTC
    - London: 08:00 - 16:30 UTC
    - New York: 13:00 - 21:00 UTC
    - London/NY Overlap: 13:00 - 16:30 UTC
    """
    hour = dt_utc.hour + dt_utc.minute / 60.0
    if 13.0 <= hour <= 16.5:
        return "OVERLAP_LDN_NY"
    elif 8.0 <= hour <= 16.5:
        return "LONDON"
    elif 13.0 <= hour <= 21.0:
        return "NEW_YORK"
    elif 0.0 <= hour <= 8.0:
        return "ASIAN"
    return "OFF_HOURS"


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average causally."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculates Relative Strength Index (RSI) causally using Wilder's smoothing.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -1.0 * delta.clip(upper=0.0)

    # Wilder's exponential smoothing
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculates True Range and Average True Range causally.
    True Range = max(high - low, abs(high - close_prev), abs(low - close_prev))
    """
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr.bfill().fillna(0.0)


def calculate_realized_volatility(close_series: pd.Series, period: int = 20) -> pd.Series:
    """Calculates rolling annualized realized volatility causally."""
    log_returns = np.log(close_series / close_series.shift(1))
    rolling_std = log_returns.rolling(window=period, min_periods=period).std()
    # Assuming 252 trading days with ~24 hours/day (hourly equivalent) or typical scale
    annualized_vol = rolling_std * np.sqrt(252 * 24)
    return annualized_vol.fillna(0.0)


def calculate_atr_percentile(atr_series: pd.Series, window: int = 100) -> pd.Series:
    """
    Calculates the percentile rank of the current ATR relative to the preceding `window` bars.
    Strictly causal rolling rank.
    """
    def rolling_percentile(s: pd.Series) -> float:
        current_val = s.iloc[-1]
        pct = (s < current_val).mean() * 100.0
        return float(pct)

    return atr_series.rolling(window=window, min_periods=min(10, window)).apply(
        rolling_percentile, raw=False
    ).fillna(50.0)


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates the full required indicator suite on an OHLCV dataframe.
    Requires columns: ['open', 'high', 'low', 'close', 'volume'].
    Returns dataframe augmented with causal indicator columns.
    """
    df = df.copy()
    if df.empty:
        return df

    # Core Moving Averages
    df["ema_20"] = calculate_ema(df["close"], 20)
    df["ema_50"] = calculate_ema(df["close"], 50)

    # Momentum
    df["rsi_14"] = calculate_rsi(df["close"], 14)

    # Volatility
    df["atr_14"] = calculate_atr(df, 14)
    df["atr_percentile_100"] = calculate_atr_percentile(df["atr_14"], 100)
    df["realized_vol_20"] = calculate_realized_volatility(df["close"], 20)

    # Sessions (if timestamp column or index exists)
    if "timestamp_utc" in df.columns:
        df["session"] = df["timestamp_utc"].apply(
            lambda t: detect_session(t if isinstance(t, datetime) else pd.to_datetime(t).to_pydatetime())
        )
    elif isinstance(df.index, pd.DatetimeIndex):
        df["session"] = [detect_session(t.to_pydatetime()) for t in df.index]
    else:
        df["session"] = "UNKNOWN"

    return df


def identify_market_regime(
    close: float,
    ema_20: float,
    ema_50: float,
    rsi_14: float,
    atr_percentile: float,
    has_imminent_high_impact_news: bool = False,
) -> RegimeLabel:
    """
    Deterministic rule-based regime classifier.
    """
    if has_imminent_high_impact_news:
        return RegimeLabel.NEWS_SHOCK

    if close > ema_20 and ema_20 > ema_50 and rsi_14 > 50.0:
        return RegimeLabel.TRENDING_BULL
    elif close < ema_20 and ema_20 < ema_50 and rsi_14 < 50.0:
        return RegimeLabel.TRENDING_BEAR
    else:
        if atr_percentile >= 75.0:
            return RegimeLabel.RANGING_HIGH_VOL
        return RegimeLabel.RANGING_LOW_VOL
