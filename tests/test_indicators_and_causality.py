"""
Unit Tests: Causal Indicators & Look-Ahead Leakage Prevention.
Proves mathematically that modifying future bars t > k does NOT alter indicator values at t <= k.
"""

from __future__ import annotations

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from src.ingestion.indicators import (
    calculate_indicators,
    detect_session,
    identify_market_regime,
)
from src.schemas.market import RegimeLabel


def test_session_tagging():
    # London
    dt_ldn = datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc)
    assert detect_session(dt_ldn) == "LONDON"

    # London / New York Overlap
    dt_overlap = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
    assert detect_session(dt_overlap) == "OVERLAP_LDN_NY"

    # Asian
    dt_asian = datetime(2026, 6, 1, 3, 0, tzinfo=timezone.utc)
    assert detect_session(dt_asian) == "ASIAN"

    # Off hours
    dt_off = datetime(2026, 6, 1, 22, 30, tzinfo=timezone.utc)
    assert detect_session(dt_off) == "OFF_HOURS"


def test_indicator_causality_and_no_lookahead_leakage(sample_market_df):
    """
    CRITICAL LEAKAGE TEST:
    Calculate indicators on baseline df. Then perturb future bars (e.g. from index 150 onwards).
    Values at index <= 149 must remain 100% IDENTICAL down to machine epsilon.
    """
    df1 = sample_market_df.copy()
    ind1 = calculate_indicators(df1)

    cutoff_idx = 150
    df2 = sample_market_df.copy()
    # Heavily corrupt future bars
    df2.loc[cutoff_idx:, "close"] = df2.loc[cutoff_idx:, "close"] * 2.5
    df2.loc[cutoff_idx:, "high"] = df2.loc[cutoff_idx:, "high"] * 3.0
    df2.loc[cutoff_idx:, "low"] = df2.loc[cutoff_idx:, "low"] * 0.5
    df2.loc[cutoff_idx:, "volume"] = 999999.0

    ind2 = calculate_indicators(df2)

    # Inspect all past indicators up to cutoff_idx - 1
    past_cols = ["ema_20", "ema_50", "rsi_14", "atr_14", "atr_percentile_100", "realized_vol_20"]
    for col in past_cols:
        diff = np.abs(ind1.loc[:cutoff_idx - 1, col] - ind2.loc[:cutoff_idx - 1, col])
        max_diff = diff.max()
        assert max_diff < 1e-10, f"Future leakage detected in column '{col}'! Max diff: {max_diff}"


def test_regime_classification():
    # Bull trend
    regime = identify_market_regime(
        close=1.0900,
        ema_20=1.0850,
        ema_50=1.0800,
        rsi_14=62.0,
        atr_percentile=50.0,
    )
    assert regime == RegimeLabel.TRENDING_BULL

    # News shock
    regime_shock = identify_market_regime(
        close=1.0900,
        ema_20=1.0850,
        ema_50=1.0800,
        rsi_14=62.0,
        atr_percentile=50.0,
        has_imminent_high_impact_news=True,
    )
    assert regime_shock == RegimeLabel.NEWS_SHOCK
