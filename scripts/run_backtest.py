"""
Runner Script: Backtest & Walk-Forward Validation.
Loads sample data, runs BacktestEngine, and outputs report.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.backtest.engine import BacktestEngine
from src.backtest.report import BacktestReporter
from src.backtest.robustness import RobustnessAnalyzer
from src.backtest.walk_forward import WalkForwardAnalyzer
from src.database.connection import init_db
from src.schemas.strategy import StrategySpec, Rule, RuleLogic
from src.strategies.generated.ema_rsi_trend import EmaRsiTrendStrategy
from scripts.generate_sample_data import generate_sample_bars


def main():
    init_db()
    data_path = BASE_DIR / "data" / "sample_bars.csv"
    if not data_path.exists():
        df = generate_sample_bars(2500)
    else:
        df = pd.read_csv(data_path)
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])

    # Construct Strategy Spec
    spec = StrategySpec(
        strategy_id="strat_ema_rsi_trend",
        version="v1.0.0",
        hypothesis_id="hyp-example-01",
        status="CODED",
        universe=["EURUSD"],
        timeframe="M15",
        entry_logic=RuleLogic.AND,
        entry_rules=[
            Rule(feature="ema_20", operator="CROSS_ABOVE", value="ema_50", lookback=1),
            Rule(feature="rsi_14", operator="<", value=70.0, lookback=1),
        ],
        exit_logic=RuleLogic.OR,
        exit_rules=[
            Rule(feature="ema_20", operator="CROSS_BELOW", value="ema_50", lookback=1),
        ],
        stop_loss_atr_mult=1.5,
        take_profit_rr=2.0,
    )

    strategy = EmaRsiTrendStrategy(spec)
    engine = BacktestEngine()

    print("\n--- Running Chronological Backtest (IS 60% / OOS 20% / Test 20%) ---")
    result = engine.run_validation_pipeline(strategy, df, evaluate_test_set=True)

    print("\n--- Running Walk-Forward Analysis (4 folds) ---")
    wfa = WalkForwardAnalyzer(folds=4, train_bars=1200, val_bars=300)
    folds = wfa.run_walk_forward(strategy, df)
    result.walk_forward_folds = folds

    print("\n--- Running Parameter Robustness Heatmap (2D Sweep) ---")
    rob = RobustnessAnalyzer()
    robustness_res = rob.run_2d_sweep(strategy, df, "ema_fast", [15, 20, 25], "rsi_period", [10, 14, 18])
    result.robustness = robustness_res

    report_md = BacktestReporter.generate_markdown_report(result)
    print("\n" + report_md)


if __name__ == "__main__":
    main()
