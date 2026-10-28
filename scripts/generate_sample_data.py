"""
Sample Market Data Generator.
Generates realistic EURUSD M15 historical bars with volatility clusters and news calendar events.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def generate_sample_bars(num_bars: int = 2500) -> pd.DataFrame:
    np.random.seed(42)
    start_time = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [start_time + timedelta(minutes=15 * i) for i in range(num_bars)]

    # Generate geometric Brownian motion with volatility regimes
    price = 1.0850
    prices = [price]
    regime = "NORMAL"

    for i in range(1, num_bars):
        # Regime switching
        if i % 400 == 0:
            regime = "HIGH_VOL" if regime == "NORMAL" else "NORMAL"

        vol = 0.0006 if regime == "HIGH_VOL" else 0.00025
        drift = 0.00002 if (i // 500) % 2 == 0 else -0.00001
        ret = np.random.normal(drift, vol)
        price = max(0.95, price * (1.0 + ret))
        prices.append(price)

    close_arr = np.array(prices)
    high_arr = close_arr + np.abs(np.random.normal(0.0004, 0.0002, num_bars))
    low_arr = close_arr - np.abs(np.random.normal(0.0004, 0.0002, num_bars))
    open_arr = np.roll(close_arr, 1)
    open_arr[0] = close_arr[0]
    volume_arr = np.random.uniform(200, 1500, num_bars)
    spread_arr = np.random.uniform(0.00010, 0.00018, num_bars)

    df = pd.DataFrame({
        "timestamp_utc": timestamps,
        "open": np.round(open_arr, 5),
        "high": np.round(high_arr, 5),
        "low": np.round(low_arr, 5),
        "close": np.round(close_arr, 5),
        "volume": np.round(volume_arr, 1),
        "spread": np.round(spread_arr, 5),
    })

    csv_path = DATA_DIR / "sample_bars.csv"
    df.to_csv(csv_path, index=False)
    print(f"Generated {num_bars} sample bars saved to {csv_path}")
    return df


def generate_sample_calendar() -> None:
    events = [
        {
            "time_utc": "2026-10-26T13:30:00Z",
            "currency": "USD",
            "impact": "HIGH",
            "title": "US Non-Farm Payrolls & Unemployment Rate",
            "minutes_until": 15.0,
        },
        {
            "time_utc": "2026-10-26T14:00:00Z",
            "currency": "EUR",
            "impact": "HIGH",
            "title": "ECB Monetary Policy Statement",
            "minutes_until": 45.0,
        },
        {
            "time_utc": "2026-10-26T18:00:00Z",
            "currency": "USD",
            "impact": "MEDIUM",
            "title": "FOMC Meeting Minutes",
            "minutes_until": 285.0,
        },
    ]
    cal_path = DATA_DIR / "news_calendar.json"
    with open(cal_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)
    print(f"Sample calendar saved to {cal_path}")


if __name__ == "__main__":
    generate_sample_bars(2500)
    generate_sample_calendar()
