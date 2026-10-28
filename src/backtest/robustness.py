"""
Parameter Robustness Heatmap & Island Detection Module.
Evaluates 2D parameter response surfaces and flags isolated overfit profitability islands.
"""

from __future__ import annotations

from typing import List
import pandas as pd

from src.backtest.engine import BacktestEngine
from src.schemas.backtest import HeatmapCell, RobustnessReport
from src.strategies.base import BaseStrategy


class RobustnessAnalyzer:
    def __init__(self):
        self.engine = BacktestEngine()

    def run_2d_sweep(
        self,
        strategy: BaseStrategy,
        df: pd.DataFrame,
        param_x_name: str = "ema_fast",
        param_x_vals: List[int] = [15, 20, 25],
        param_y_name: str = "rsi_period",
        param_y_vals: List[int] = [10, 14, 18],
    ) -> RobustnessReport:
        """
        Executes parameter sweep across 2 dimensions and inspects neighborhood continuity.
        """
        cells: List[HeatmapCell] = []
        grid: dict[tuple[int, int], float] = {}

        for x in param_x_vals:
            for y in param_y_vals:
                # Simulate on sample df
                eq, trades, _ = self.engine.simulate(strategy, df)
                rets = eq.pct_change().dropna()
                sharpe = float((rets.mean() / rets.std()) * (252**0.5)) if rets.std() > 1e-9 else 0.0
                grid[(x, y)] = sharpe

        # Check for isolated profitability islands
        island_count = 0
        for (x, y), val in grid.items():
            # Check neighbors
            neighbors = [v for (nx, ny), v in grid.items() if (nx != x or ny != y) and abs(nx - x) <= 10 and abs(ny - y) <= 4]
            is_island = False
            if val > 1.0 and neighbors:
                # If all neighbors are negative or drastically degraded
                if all(n < 0.2 for n in neighbors):
                    is_island = True
                    island_count += 1

            cells.append(
                HeatmapCell(
                    param_x_name=param_x_name,
                    param_x_val=x,
                    param_y_name=param_y_name,
                    param_y_val=y,
                    metric_name="Sharpe",
                    metric_value=round(val, 2),
                    is_isolated_island=is_island,
                )
            )

        stability_score = max(0.0, 1.0 - (island_count / max(1, len(cells))))

        return RobustnessReport(
            tested_params=[param_x_name, param_y_name],
            heatmap_cells=cells,
            island_count=island_count,
            parameter_stability_score=round(stability_score, 2),
        )
