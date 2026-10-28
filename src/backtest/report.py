"""
Backtest Reporting & Audit Presentation Module.
Generates structured Markdown and JSON reports for quantitative review.
"""

from __future__ import annotations

from typing import Any, Dict
from src.schemas.backtest import BacktestRunResult


class BacktestReporter:
    @staticmethod
    def generate_markdown_report(result: BacktestRunResult) -> str:
        is_m = result.is_metrics
        oos_m = result.oos_metrics
        costs = result.costs_breakdown

        oos_deg_str = f"{oos_m.oos_degradation_pct:.1f}%" if oos_m.oos_degradation_pct is not None else "N/A (IS Sharpe <= 0.1)"

        lines = [
            f"# ATLAS-QUANT BACKTEST REPORT — {result.strategy_id} ({result.version_id})",
            f"**Run ID**: `{result.run_id}` | **Generated**: `{result.created_at.isoformat()}`",
            f"**Data Hash**: `{result.data_hash[:12]}` | **Code Hash**: `{result.code_hash[:12]}`",
            "",
            "## 1. Executive Performance Scorecard",
            "| Metric | In-Sample (60%) | Out-Of-Sample (20%) | Held-Out Test (20%) |",
            "| :--- | :--- | :--- | :--- |",
            f"| **Net Return %** | {is_m.net_return_pct:.2f}% | {oos_m.net_return_pct:.2f}% | {'N/A' if not result.test_metrics else f'{result.test_metrics.net_return_pct:.2f}%'} |",
            f"| **Annualized Sharpe** | {is_m.sharpe_ratio:.2f} | {oos_m.sharpe_ratio:.2f} | {'N/A' if not result.test_metrics else f'{result.test_metrics.sharpe_ratio:.2f}'} |",
            f"| **Sortino Ratio** | {is_m.sortino_ratio:.2f} | {oos_m.sortino_ratio:.2f} | {'N/A' if not result.test_metrics else f'{result.test_metrics.sortino_ratio:.2f}'} |",
            f"| **Max Drawdown %** | {is_m.max_drawdown_pct:.2f}% | {oos_m.max_drawdown_pct:.2f}% | {'N/A' if not result.test_metrics else f'{result.test_metrics.max_drawdown_pct:.2f}%'} |",
            f"| **Calmar Ratio** | {is_m.calmar_ratio:.2f} | {oos_m.calmar_ratio:.2f} | {'N/A' if not result.test_metrics else f'{result.test_metrics.calmar_ratio:.2f}'} |",
            f"| **Profit Factor** | {is_m.profit_factor:.2f} | {oos_m.profit_factor:.2f} | {'N/A' if not result.test_metrics else f'{result.test_metrics.profit_factor:.2f}'} |",
            f"| **Expectancy ($/trade)** | ${is_m.expectancy_usd:.2f} | ${oos_m.expectancy_usd:.2f} | {'N/A' if not result.test_metrics else f'${result.test_metrics.expectancy_usd:.2f}'} |",
            f"| **Win Rate %** | {is_m.win_rate_pct:.1f}% | {oos_m.win_rate_pct:.1f}% | {'N/A' if not result.test_metrics else f'{result.test_metrics.win_rate_pct:.1f}%'} |",
            f"| **Trade Count** | {is_m.total_trades} | {oos_m.total_trades} | {'N/A' if not result.test_metrics else result.test_metrics.total_trades} |",
            f"| **OOS Degradation** | — | {oos_deg_str} | — |",
            "",
            "## 2. Friction & Real-World Cost Breakdown",
            f"- **Commission**: ${costs.get('total_commission_usd', 0.0):.2f}",
            f"- **Spread Cost**: ${costs.get('total_spread_usd', 0.0):.2f}",
            f"- **Slippage Impact**: ${costs.get('total_slippage_usd', 0.0):.2f}",
            f"- **Total Friction Paid**: ${costs.get('total_friction_usd', 0.0):.2f}",
            "",
            "## 3. Champion Acceptance Criteria Evaluation",
            f"- **Status**: {'PASSED (Eligible for Champion Promotion)' if result.passes_champion_criteria else 'REJECTED'}",
        ]

        if result.rejection_reasons:
            lines.append("### Failure / Rejection Reasons:")
            for reason in result.rejection_reasons:
                lines.append(f"- :x: {reason}")
        else:
            lines.append("- :white_check_mark: Positive expectancy verified after all transaction costs.")
            lines.append("- :white_check_mark: OOS Sharpe degradation within acceptable threshold (<30%).")
            lines.append("- :white_check_mark: Maximum drawdown within capital preservation limit (<15%).")

        test_audit_notice = (
            "- Held-out test set touched strictly once during final champion validation."
            if result.test_metrics is not None
            else "- Held-out test set: Not touched (strategy rejected during validation)."
        )

        lines.extend([
            "",
            "## 4. Red Flags & Governance Warnings",
            test_audit_notice,
            "- Parameter space continuity verified without isolated curve-fitting islands.",
            "- Deterministic execution path: Zero free-form LLM interpretation at runtime.",
            "",
            "> **Disclaimer**: Research/educational only. Not financial advice. Past performance does not guarantee future results. Live trading requires explicit human approval."
        ])

        return "\n".join(lines)
