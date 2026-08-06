"""Backtest Reporting: Monthly/Yearly Returns Matrix, Drawdown Breakdown, and Markdown Export."""
from collections import defaultdict
from datetime import datetime
from typing import Any


class BacktestReportGenerator:
    """Generates structured analytics tables and formatted reports for backtests."""

    @staticmethod
    def generate_monthly_returns_table(equity_curve: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        """Computes a matrix of Monthly Returns (Jan..Dec) and Year-to-Date (YTD) returns.
        Output format: { "2024": { "Jan": 2.34, "Feb": -1.12, ..., "YTD": 15.6 } }
        """
        if len(equity_curve) < 2:
            return {}

        # Parse timestamps and equity values
        points: list[tuple[datetime, float]] = []
        for pt in equity_curve:
            ts_str = pt["ts"]
            if isinstance(ts_str, str):
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            else:
                ts = ts_str
            points.append((ts, float(pt["equity"])))

        points.sort(key=lambda x: x[0])

        # Group by year and month: (year, month) -> (first_eq, last_eq)
        month_groups: dict[tuple[int, int], list[float]] = defaultdict(list)
        for ts, eq in points:
            month_groups[(ts.year, ts.month)].append(eq)

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        years = sorted(list({y for y, _ in month_groups.keys()}))

        matrix: dict[str, dict[str, float]] = {}

        for yr in years:
            matrix[str(yr)] = {}
            yr_equity_start = None
            yr_equity_end = None

            for m_idx, m_name in enumerate(month_names, start=1):
                key = (yr, m_idx)
                if key in month_groups:
                    eq_vals = month_groups[key]
                    m_start = eq_vals[0]
                    m_end = eq_vals[-1]
                    if yr_equity_start is None:
                        yr_equity_start = m_start
                    yr_equity_end = m_end
                    m_ret = ((m_end - m_start) / m_start * 100.0) if m_start > 0 else 0.0
                    matrix[str(yr)][m_name] = round(m_ret, 2)
                else:
                    matrix[str(yr)][m_name] = 0.0

            if yr_equity_start and yr_equity_end:
                ytd_ret = ((yr_equity_end - yr_equity_start) / yr_equity_start * 100.0) if yr_equity_start > 0 else 0.0
                matrix[str(yr)]["YTD"] = round(ytd_ret, 2)
            else:
                matrix[str(yr)]["YTD"] = 0.0

        return matrix

    @staticmethod
    def generate_drawdown_table(equity_curve: list[dict[str, Any]], top_n: int = 5) -> list[dict[str, Any]]:
        """Identifies top N worst drawdown periods (peak, trough, recovery, max DD %, duration)."""
        if len(equity_curve) < 2:
            return []

        drawdowns: list[dict[str, Any]] = []
        peak_eq = float(equity_curve[0]["equity"])
        peak_ts = equity_curve[0]["ts"]
        trough_eq = peak_eq
        trough_ts = peak_ts

        in_drawdown = False
        current_dd_list: list[dict[str, Any]] = []

        for pt in equity_curve:
            eq = float(pt["equity"])
            ts = pt["ts"]

            if eq >= peak_eq:
                if in_drawdown and peak_eq > 0:
                    dd_pct = (peak_eq - trough_eq) / peak_eq * 100.0
                    if dd_pct >= 0.5:  # filter noise < 0.5%
                        current_dd_list.append({
                            "peak_date": str(peak_ts),
                            "trough_date": str(trough_ts),
                            "recovery_date": str(ts),
                            "drawdown_pct": round(dd_pct, 2),
                        })
                in_drawdown = False
                peak_eq = eq
                peak_ts = ts
                trough_eq = eq
                trough_ts = ts
            else:
                in_drawdown = True
                if eq < trough_eq:
                    trough_eq = eq
                    trough_ts = ts

        # If currently in drawdown at end of simulation
        if in_drawdown and peak_eq > 0:
            dd_pct = (peak_eq - trough_eq) / peak_eq * 100.0
            if dd_pct >= 0.5:
                current_dd_list.append({
                    "peak_date": str(peak_ts),
                    "trough_date": str(trough_ts),
                    "recovery_date": "Active (Not recovered)",
                    "drawdown_pct": round(dd_pct, 2),
                })

        current_dd_list.sort(key=lambda d: d["drawdown_pct"], reverse=True)
        return current_dd_list[:top_n]

    @staticmethod
    def generate_markdown_report(
        backtest_name: str,
        strategy_id: str,
        metrics: dict[str, Any],
        config_snapshot: dict[str, Any],
        monthly_returns: dict[str, dict[str, float]],
        top_drawdowns: list[dict[str, Any]],
    ) -> str:
        """Generates a complete GitHub-flavored markdown report."""
        lines = [
            f"# Backtest Performance Report: {backtest_name}",
            f"**Strategy**: `{strategy_id}` · **Generated**: `{datetime.utcnow().isoformat()}`",
            "",
            "## 1. Key Performance Indicators",
            "",
            "| Metric | Value | Metric | Value |",
            "| :--- | :--- | :--- | :--- |",
            f"| **Total Return** | `{metrics.get('total_return_pct', 0.0)}%` | **CAGR** | `{metrics.get('cagr_pct', 0.0)}%` |",
            f"| **Sharpe Ratio** | `{metrics.get('sharpe_ratio', 0.0)}` | **Sortino Ratio** | `{metrics.get('sortino_ratio', 0.0)}` |",
            f"| **Calmar Ratio** | `{metrics.get('calmar_ratio', 0.0)}` | **Max Drawdown** | `{metrics.get('max_drawdown_pct', 0.0)}%` |",
            f"| **Win Rate** | `{metrics.get('win_rate_pct', 0.0)}%` | **Profit Factor** | `{metrics.get('profit_factor', 0.0)}` |",
            f"| **Total Trades** | `{metrics.get('total_trades', 0)}` | **Expectancy** | `₹{metrics.get('expectancy', 0.0)}` |",
            f"| **Deflated Sharpe (DSR)** | `{metrics.get('deflated_sharpe_ratio', 0.0)}` | **Prob. Overfitting (PBO)** | `{metrics.get('probability_of_backtest_overfitting', 0.0)}` |",
            "",
            "## 2. Monthly Returns Matrix (%)",
            "",
        ]

        if monthly_returns:
            headers = ["Year", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "YTD"]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join([":---"] * len(headers)) + " |")
            for yr, months in monthly_returns.items():
                row = [yr] + [f"{months.get(m, 0.0):.2f}%" for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]] + [f"**{months.get('YTD', 0.0):.2f}%**"]
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")

        lines.extend([
            "## 3. Top Drawdown Periods",
            "",
            "| Peak Date | Trough Date | Recovery Date | Max Drawdown |",
            "| :--- | :--- | :--- | :--- |",
        ])
        for dd in top_drawdowns:
            lines.append(f"| {dd['peak_date']} | {dd['trough_date']} | {dd['recovery_date']} | **{dd['drawdown_pct']}%** |")

        return "\n".join(lines)
