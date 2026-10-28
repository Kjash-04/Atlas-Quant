"""
Backtesting engine and rigorous statistical validation suite.
"""

from src.backtest.costs import RealisticCostModel
from src.backtest.metrics import calculate_performance_metrics
from src.backtest.engine import BacktestEngine
from src.backtest.walk_forward import WalkForwardAnalyzer
from src.backtest.robustness import RobustnessAnalyzer
from src.backtest.report import BacktestReporter

__all__ = [
    "RealisticCostModel",
    "calculate_performance_metrics",
    "BacktestEngine",
    "WalkForwardAnalyzer",
    "RobustnessAnalyzer",
    "BacktestReporter",
]
