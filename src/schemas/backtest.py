"""
Backtest Metrics & Reporting Schemas.
Chronological splits (IS/OOS/Test), cost attribution, and parameter robustness metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class BacktestMetrics(BaseModel):
    net_return_pct: float = 0.0
    cagr_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    calmar_ratio: float = 0.0
    profit_factor: float = 0.0
    expectancy_usd: float = 0.0
    win_rate_pct: float = 0.0
    total_trades: int = 0
    avg_trade_pnl: float = 0.0
    turnover: float = 0.0
    oos_degradation_pct: Optional[float] = None
    slippage_sensitivity_pct: float = 0.0
    worst_day_loss_pct: float = 0.0
    estimated_capacity_usd: float = 100000.0


class WalkForwardFoldResult(BaseModel):
    fold_index: int
    train_start: str
    train_end: str
    val_start: str
    val_end: str
    optimal_params: Dict[str, Any]
    train_sharpe: float
    val_sharpe: float
    val_drawdown: float
    parameter_stable: bool = True


class HeatmapCell(BaseModel):
    param_x_name: str
    param_x_val: Any
    param_y_name: str
    param_y_val: Any
    metric_name: str
    metric_value: float
    is_isolated_island: bool = False


class RobustnessReport(BaseModel):
    tested_params: List[str]
    heatmap_cells: List[HeatmapCell]
    island_count: int = 0
    parameter_stability_score: float = 1.0


class BacktestRunResult(BaseModel):
    run_id: str
    strategy_id: str
    version_id: str
    data_hash: str
    code_hash: str
    param_hash: str
    is_metrics: BacktestMetrics
    oos_metrics: BacktestMetrics
    test_metrics: Optional[BacktestMetrics] = None  # Touched once for champion
    walk_forward_folds: List[WalkForwardFoldResult] = Field(default_factory=list)
    robustness: Optional[RobustnessReport] = None
    costs_breakdown: Dict[str, float] = Field(default_factory=dict)
    red_flags: List[str] = Field(default_factory=list)
    passes_champion_criteria: bool = False
    rejection_reasons: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
