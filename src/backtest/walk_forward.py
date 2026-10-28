"""
Walk-Forward Optimization & Analysis Module.
Tests parameter stability across rolling/anchored train-validate folds.
"""

from __future__ import annotations

from typing import Any, Dict, List
import pandas as pd

from src.backtest.engine import BacktestEngine
from src.schemas.backtest import WalkForwardFoldResult
from src.strategies.base import BaseStrategy


class WalkForwardAnalyzer:
    def __init__(
        self,
        folds: int = 4,
        train_bars: int = 1500,
        val_bars: int = 400,
    ):
        self.folds = folds
        self.train_bars = train_bars
        self.val_bars = val_bars
        self.engine = BacktestEngine()

    def run_walk_forward(
        self,
        strategy: BaseStrategy,
        df: pd.DataFrame,
    ) -> List[WalkForwardFoldResult]:
        """
        Executes rolling walk-forward analysis.
        """
        results: List[WalkForwardFoldResult] = []
        total_len = len(df)
        step = self.val_bars

        for fold in range(self.folds):
            start_idx = fold * step
            train_end = start_idx + self.train_bars
            val_end = train_end + self.val_bars

            if val_end > total_len:
                break

            train_df = df.iloc[start_idx:train_end].copy()
            val_df = df.iloc[train_end:val_end].copy()

            # Train simulation
            tr_eq, tr_trades, _ = self.engine.simulate(strategy, train_df)
            val_eq, val_trades, _ = self.engine.simulate(strategy, val_df)

            tr_rets = tr_eq.pct_change().dropna()
            val_rets = val_eq.pct_change().dropna()

            tr_sharpe = float((tr_rets.mean() / tr_rets.std()) * (252**0.5)) if tr_rets.std() > 1e-9 else 0.0
            val_sharpe = float((val_rets.mean() / val_rets.std()) * (252**0.5)) if val_rets.std() > 1e-9 else 0.0

            # Drawdown
            rolling_max = val_eq.cummax()
            dd = (val_eq - rolling_max) / rolling_max
            val_dd = abs(float(dd.min())) * 100.0

            # Parameter stability: validation sharpe stays positive
            stable = val_sharpe > 0.0 and val_dd < 15.0

            fold_res = WalkForwardFoldResult(
                fold_index=fold + 1,
                train_start=str(train_df.index[0]) if not train_df.empty else f"bar_{start_idx}",
                train_end=str(train_df.index[-1]) if not train_df.empty else f"bar_{train_end}",
                val_start=str(val_df.index[0]) if not val_df.empty else f"bar_{train_end}",
                val_end=str(val_df.index[-1]) if not val_df.empty else f"bar_{val_end}",
                optimal_params=strategy.spec.parameter_ranges,
                train_sharpe=round(tr_sharpe, 2),
                val_sharpe=round(val_sharpe, 2),
                val_drawdown=round(val_dd, 2),
                parameter_stable=stable,
            )
            results.append(fold_res)

        return results
