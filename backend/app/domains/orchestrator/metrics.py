"""Continuous financial metrics tracking and equity curve analytics."""
from datetime import datetime, timezone
from decimal import Decimal
import math
from typing import Sequence
import uuid

from app.domains.metrics.calculator import PerformanceMetricsCalculator
from app.domains.orchestrator.schemas import ContinuousMetricsResponse
from app.domains.trading.models import Portfolio, Position


class ContinuousMetricsTracker:
    """Tracks continuous portfolio equity curves and calculates live risk-adjusted returns."""

    def __init__(self):
        self._equity_history: dict[uuid.UUID, list[tuple[datetime, Decimal]]] = {}
        self._trade_pnls: dict[uuid.UUID, list[Decimal]] = {}

    def record_equity_point(
        self,
        portfolio_id: uuid.UUID,
        timestamp: datetime,
        total_equity: Decimal,
    ) -> None:
        """Records a timestamped total equity observation."""
        if portfolio_id not in self._equity_history:
            self._equity_history[portfolio_id] = []
        self._equity_history[portfolio_id].append((timestamp, total_equity))

    def record_closed_trade_pnl(self, portfolio_id: uuid.UUID, pnl: Decimal) -> None:
        """Records the realized PnL of a closed trade."""
        if portfolio_id not in self._trade_pnls:
            self._trade_pnls[portfolio_id] = []
        self._trade_pnls[portfolio_id].append(pnl)

    def calculate_metrics(
        self,
        portfolio: Portfolio,
        open_positions: Sequence[Position],
        current_time: datetime,
        current_prices: dict[uuid.UUID, Decimal] | None = None,
    ) -> ContinuousMetricsResponse:
        """Computes live Sharpe, Drawdown, Win Rate, and turnover metrics."""
        prices = current_prices or {}
        
        # Calculate current open positions market value
        pos_value = Decimal("0.00")
        for pos in open_positions:
            qty = pos.quantity
            if qty > 0:
                entry_p = getattr(pos, "avg_entry_price", getattr(pos, "average_entry_price", Decimal("0.00")))
                p = prices.get(pos.instrument_id, entry_p)
                pos_value += qty * p

        total_equity = portfolio.cash_balance + portfolio.reserved_cash + pos_value
        self.record_equity_point(portfolio.id, current_time, total_equity)

        # Equity series for Sharpe / Drawdown
        history = self._equity_history.get(portfolio.id, [])
        equity_series = [float(eq) for _, eq in history]
        timestamps = [ts for ts, _ in history]

        # Drawdown calculation
        max_dd_pct = 0.0
        if equity_series:
            peak = equity_series[0]
            for val in equity_series:
                if val > peak:
                    peak = val
                if peak > 0:
                    dd = (peak - val) / peak * 100.0
                    if dd > max_dd_pct:
                        max_dd_pct = dd

        # Returns and Sharpe / Sortino
        returns = []
        if len(equity_series) >= 2:
            for i in range(1, len(equity_series)):
                if equity_series[i - 1] > 0:
                    returns.append((equity_series[i] - equity_series[i - 1]) / equity_series[i - 1])

        sharpe: float | None = None
        sortino: float | None = None
        if len(returns) >= 2:
            mean_ret = sum(returns) / len(returns)
            variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
            std_dev = math.sqrt(variance)
            if std_dev > 1e-8:
                sharpe = round((mean_ret / std_dev) * math.sqrt(252), 3)

            neg_returns = [r for r in returns if r < 0]
            if neg_returns:
                downside_var = sum(r ** 2 for r in neg_returns) / len(neg_returns)
                downside_std = math.sqrt(downside_var)
                if downside_std > 1e-8:
                    sortino = round((mean_ret / downside_std) * math.sqrt(252), 3)

        # Trade stats
        pnls = self._trade_pnls.get(portfolio.id, [])
        total_trades = len(pnls)
        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p < 0]

        win_rate = (len(winning) / total_trades * 100.0) if total_trades > 0 else 0.0
        gross_profit = sum(winning) if winning else Decimal("0.00")
        gross_loss = abs(sum(losing)) if losing else Decimal("0.00")
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        expectancy = float(sum(pnls) / total_trades) if total_trades > 0 else 0.0

        cash_util = (float(pos_value / total_equity) * 100.0) if total_equity > 0 else 0.0
        total_pnl = total_equity - portfolio.initial_capital

        return ContinuousMetricsResponse(
            portfolio_id=portfolio.id,
            timestamp=current_time,
            total_equity=total_equity,
            cash_balance=portfolio.cash_balance,
            total_pnl=total_pnl,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=round(float(total_pnl / portfolio.initial_capital) * 100.0 / max_dd_pct, 3) if max_dd_pct > 0 else None,
            max_drawdown_pct=round(max_dd_pct, 2),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            expectancy=round(expectancy, 2),
            turnover_ratio=0.0,
            cash_utilization_pct=round(cash_util, 2),
            total_trades=total_trades,
        )
