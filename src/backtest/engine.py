"""
Rigorous Chronological Backtesting Engine.
Enforces In-Sample (60%), Out-Of-Sample (20%), and Held-out Test (20%) boundaries.
Includes purging/embargo to eliminate boundary leakage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from src.backtest.costs import RealisticCostModel
from src.backtest.metrics import calculate_performance_metrics
from src.database.connection import SessionLocal
from src.database.models import BacktestRunModel
from src.schemas.backtest import BacktestMetrics, BacktestRunResult
from src.schemas.strategy import StrategySpec
from src.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100000.0,
        cost_model: Optional[RealisticCostModel] = None,
        is_ratio: float = 0.60,
        oos_ratio: float = 0.20,
        test_ratio: float = 0.20,
        embargo_bars: int = 20,
    ):
        self.initial_capital = initial_capital
        self.cost_model = cost_model or RealisticCostModel()
        self.is_ratio = is_ratio
        self.oos_ratio = oos_ratio
        self.test_ratio = test_ratio
        self.embargo_bars = embargo_bars

    def split_data(
        self, df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Splits dataframe chronologically:
        In-Sample (60%) -> Embargo -> Out-Of-Sample (20%) -> Embargo -> Test Set (20%).
        """
        n = len(df)
        is_end = int(n * self.is_ratio)
        oos_start = is_end + self.embargo_bars
        oos_end = int(n * (self.is_ratio + self.oos_ratio))
        test_start = oos_end + self.embargo_bars

        is_df = df.iloc[:is_end].copy()
        oos_df = df.iloc[oos_start:oos_end].copy()
        test_df = df.iloc[test_start:].copy()

        return is_df, oos_df, test_df

    def simulate(
        self,
        strategy: BaseStrategy,
        df: pd.DataFrame,
    ) -> Tuple[pd.Series, List[float], Dict[str, float]]:
        """
        Simulates strategy bar-by-bar causality.
        """
        if df.empty or len(df) < 10:
            return pd.Series([self.initial_capital]), [], {
                "total_commission_usd": 0.0,
                "total_spread_usd": 0.0,
                "total_slippage_usd": 0.0,
                "total_friction_usd": 0.0,
            }

        df_ind = strategy.compute_indicators(df)
        signals = strategy.generate_signals(df_ind)

        equity = self.initial_capital
        equity_curve = [equity]
        trade_pnls: List[float] = []

        total_commission = 0.0
        total_spread = 0.0
        total_slippage = 0.0

        current_pos = 0  # 1 for Long, -1 for Short, 0 for Flat
        entry_price = 0.0
        stop_price = 0.0
        target_price = 0.0
        lots = 0.0
        bars_held = 0

        # Bar-by-bar execution loop
        for i in range(1, len(df_ind)):
            row = df_ind.iloc[i]
            prev_row = df_ind.iloc[i - 1]
            signal = signals.iloc[i - 1]  # Signal evaluated on closed prior bar (NO LEAKAGE)

            close = float(row["close"])
            high = float(row["high"])
            low = float(row["low"])
            atr = float(row.get("atr_14", 0.0015))
            session = str(row.get("session", "LONDON"))

            # Check exits if position is open
            if current_pos != 0:
                bars_held += 1
                exit_triggered = False
                raw_exit_price = close

                # Check Stop Loss / Take Profit hits within high/low
                if current_pos == 1:
                    if low <= stop_price:
                        raw_exit_price = stop_price
                        exit_triggered = True
                    elif high >= target_price:
                        raw_exit_price = target_price
                        exit_triggered = True
                    elif signal == -1:  # Reverse signal
                        raw_exit_price = close
                        exit_triggered = True
                elif current_pos == -1:
                    if high >= stop_price:
                        raw_exit_price = stop_price
                        exit_triggered = True
                    elif low <= target_price:
                        raw_exit_price = target_price
                        exit_triggered = True
                    elif signal == 1:
                        raw_exit_price = close
                        exit_triggered = True

                if exit_triggered:
                    side_str = "BUY" if current_pos == 1 else "SELL"
                    _, eff_exit, friction_usd, _, bdown = self.cost_model.compute_trade_costs(
                        lots=lots,
                        entry_price=entry_price,
                        exit_price=raw_exit_price,
                        side=side_str,
                        atr=atr,
                        session=session,
                        bars_held=bars_held,
                    )
                    total_commission += bdown["commission_usd"]
                    total_spread += bdown["spread_usd"]
                    total_slippage += bdown["slippage_usd"]

                    point_val = 100000.0
                    if current_pos == 1:
                        pnl = (eff_exit - entry_price) * lots * point_val - friction_usd
                    else:
                        pnl = (entry_price - eff_exit) * lots * point_val - friction_usd

                    equity += pnl
                    trade_pnls.append(pnl)

                    # Reset position
                    current_pos = 0
                    entry_price = 0.0
                    lots = 0.0
                    bars_held = 0

            # Check entries if flat
            if current_pos == 0 and signal != 0:
                side_str = "BUY" if signal == 1 else "SELL"
                lots = strategy.size_position(equity=equity, atr=atr)
                raw_entry = close
                eff_entry, _, friction_usd, _, bdown = self.cost_model.compute_trade_costs(
                    lots=lots,
                    entry_price=raw_entry,
                    exit_price=raw_entry,
                    side=side_str,
                    atr=atr,
                    session=session,
                )
                total_commission += bdown["commission_usd"]
                total_spread += bdown["spread_usd"]
                total_slippage += bdown["slippage_usd"]

                current_pos = int(signal)
                entry_price = eff_entry
                stop_dist = max(atr * strategy.spec.stop_loss_atr_mult, 0.0005)
                target_dist = stop_dist * strategy.spec.take_profit_rr

                if current_pos == 1:
                    stop_price = entry_price - stop_dist
                    target_price = entry_price + target_dist
                else:
                    stop_price = entry_price + stop_dist
                    target_price = entry_price - target_dist
                bars_held = 0

            equity_curve.append(equity)

        cost_breakdown = {
            "total_commission_usd": round(total_commission, 2),
            "total_spread_usd": round(total_spread, 2),
            "total_slippage_usd": round(total_slippage, 2),
            "total_friction_usd": round(total_commission + total_spread + total_slippage, 2),
        }
        return pd.Series(equity_curve), trade_pnls, cost_breakdown

    def run_validation_pipeline(
        self,
        strategy: BaseStrategy,
        full_df: pd.DataFrame,
        db: Optional[Session] = None,
        evaluate_test_set: bool = False,
    ) -> BacktestRunResult:
        """
        Executes complete validation:
        1. In-Sample backtest
        2. Out-of-Sample backtest
        3. Evaluates against CHAMPION criteria
        4. Optional Held-out test evaluation (touched once)
        5. Persists report in DB
        """
        run_id = f"bt_{uuid.uuid4().hex[:8]}"
        is_df, oos_df, test_df = self.split_data(full_df)

        # 1. In-Sample
        is_equity, is_trades, is_costs = self.simulate(strategy, is_df)
        is_metrics = calculate_performance_metrics(is_equity, is_trades, self.initial_capital)

        # 2. Out-of-Sample
        oos_equity, oos_trades, oos_costs = self.simulate(strategy, oos_df)
        oos_metrics = calculate_performance_metrics(oos_equity, oos_trades, self.initial_capital)

        # Degradation metric
        if is_metrics.sharpe_ratio > 0.1:
            deg = ((is_metrics.sharpe_ratio - oos_metrics.sharpe_ratio) / is_metrics.sharpe_ratio) * 100.0
            oos_metrics.oos_degradation_pct = round(max(0.0, deg), 2)

        # 3. Champion Acceptance Criteria Evaluation
        rejection_reasons: List[str] = []
        passes_champion = True

        if is_metrics.expectancy_usd <= 0.0:
            passes_champion = False
            rejection_reasons.append(f"In-sample expectancy ${is_metrics.expectancy_usd:.2f} <= $0")
        if oos_metrics.expectancy_usd <= 0.0:
            passes_champion = False
            rejection_reasons.append(f"Out-of-sample expectancy ${oos_metrics.expectancy_usd:.2f} <= $0")
        if is_metrics.sharpe_ratio > 0.5 and oos_metrics.sharpe_ratio < (0.70 * is_metrics.sharpe_ratio):
            passes_champion = False
            rejection_reasons.append(
                f"OOS Sharpe ({oos_metrics.sharpe_ratio}) degraded below 70% of IS Sharpe ({is_metrics.sharpe_ratio})"
            )
        if oos_metrics.max_drawdown_pct > 15.0:
            passes_champion = False
            rejection_reasons.append(f"OOS Max Drawdown {oos_metrics.max_drawdown_pct:.1f}% exceeds 15.0% threshold")

        test_metrics = None
        if evaluate_test_set and passes_champion:
            test_equity, test_trades, _ = self.simulate(strategy, test_df)
            test_metrics = calculate_performance_metrics(test_equity, test_trades, self.initial_capital)

        # Hashes
        data_hash = hashlib.sha256(str(len(full_df)).encode()).hexdigest()
        code_hash = strategy.spec.code_hash
        param_hash = hashlib.sha256(json.dumps(strategy.spec.parameter_ranges, sort_keys=True).encode()).hexdigest()

        result = BacktestRunResult(
            run_id=run_id,
            strategy_id=strategy.strategy_id,
            version_id=strategy.version,
            data_hash=data_hash,
            code_hash=code_hash,
            param_hash=param_hash,
            is_metrics=is_metrics,
            oos_metrics=oos_metrics,
            test_metrics=test_metrics,
            costs_breakdown=oos_costs,
            passes_champion_criteria=passes_champion,
            rejection_reasons=rejection_reasons,
        )

        # Persist run to DB
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            model = BacktestRunModel(
                run_id=run_id,
                strategy_id=strategy.strategy_id,
                version_id=strategy.version,
                data_hash=data_hash,
                code_hash=code_hash,
                param_hash=param_hash,
                is_metrics=is_metrics.model_dump(mode="json"),
                oos_metrics=oos_metrics.model_dump(mode="json"),
                test_metrics=test_metrics.model_dump(mode="json") if test_metrics else None,
                costs_json=oos_costs,
                passes_champion_criteria=passes_champion,
                rejection_reasons=rejection_reasons,
            )
            db.add(model)
            db.commit()
            logger.info(f"BacktestRun {run_id} persisted. Champion criteria pass={passes_champion}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist backtest run: {e}")
        finally:
            if own_session:
                db.close()

        return result
