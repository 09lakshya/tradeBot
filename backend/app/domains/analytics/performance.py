"""Portfolio Performance Analytics Engine — Gross and Net performance calculation."""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.analytics.models import EquitySnapshot, TradeJournalEntry
from app.domains.analytics.schemas import (
    GrossNetPerformanceReport,
    PerformanceMetrics,
    ReturnEntry,
)
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.metrics.calculator import PerformanceMetricsCalculator, PerformanceReport
from app.domains.platform.logging import get_structured_logger
from app.domains.trading.models import Portfolio

log = get_structured_logger(__name__)


def _report_to_metrics(report: PerformanceReport) -> PerformanceMetrics:
    """Convert a raw PerformanceReport into the analytics PerformanceMetrics schema."""
    return PerformanceMetrics(
        total_return_pct=round(report.total_return_pct, 4),
        cagr_pct=round(report.cagr_pct, 4),
        annualized_volatility_pct=round(report.annualized_volatility_pct, 4),
        sharpe_ratio=round(report.sharpe_ratio, 4),
        sortino_ratio=round(report.sortino_ratio, 4),
        calmar_ratio=round(report.calmar_ratio, 4),
        information_ratio=round(report.information_ratio, 4) if report.information_ratio is not None else None,
        alpha=round(report.alpha, 4) if report.alpha is not None else None,
        beta=round(report.beta, 4) if report.beta is not None else None,
        win_rate_pct=round(report.win_rate_pct, 4),
        loss_rate_pct=round(100.0 - report.win_rate_pct, 4),
        profit_factor=round(report.profit_factor, 4),
        expectancy=round(report.expectancy, 4),
        average_win=round(report.avg_trade_pnl if report.winning_trades > 0 else 0.0, 4),
        average_loss=round(abs(report.avg_trade_pnl) if report.losing_trades > 0 else 0.0, 4),
        max_drawdown_pct=round(report.max_drawdown_pct, 4),
        max_drawdown_duration_days=report.max_drawdown_duration_days,
        max_consecutive_wins=report.max_consecutive_wins,
        max_consecutive_losses=report.max_consecutive_losses,
        total_trades=report.total_trades,
        winning_trades=report.winning_trades,
        losing_trades=report.losing_trades,
        omega_ratio=round(report.omega_ratio, 4),
        payoff_ratio=round(report.payoff_ratio, 4),
    )


class PerformanceAnalyticsService:
    """Calculates comprehensive gross and net performance analytics."""

    def __init__(self) -> None:
        self._journal = TradeJournalService()

    def _build_equity_series(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        field: str = "gross_equity",
    ) -> list[float]:
        """Extract an equity time-series from EquitySnapshot table."""
        from sqlalchemy import select
        stmt = (
            select(getattr(EquitySnapshot, field))
            .where(EquitySnapshot.portfolio_id == portfolio_id)
            .order_by(EquitySnapshot.timestamp)
        )
        return [float(v) for v in db.execute(stmt).scalars().all()]

    def _build_trade_pnls(
        self,
        trades: Sequence[TradeJournalEntry],
        field: str = "gross_pnl",
    ) -> list[float]:
        """Extract trade PnLs from journal entries."""
        return [float(getattr(t, field)) for t in trades]

    def calculate_gross_performance(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> PerformanceMetrics:
        """Calculate gross (before-cost) performance metrics."""
        equity_series = self._build_equity_series(db, portfolio_id, "gross_equity")
        trades = self._journal.get_all_portfolio_trades(db, portfolio_id)
        trade_pnls = self._build_trade_pnls(trades, "gross_pnl")

        if len(equity_series) < 2:
            return PerformanceMetrics()

        report = PerformanceMetricsCalculator.calculate(
            equity_series=equity_series,
            trade_pnls=trade_pnls,
        )
        return _report_to_metrics(report)

    def calculate_net_performance(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> PerformanceMetrics:
        """Calculate net (after-cost) performance metrics."""
        equity_series = self._build_equity_series(db, portfolio_id, "net_equity")
        trades = self._journal.get_all_portfolio_trades(db, portfolio_id)
        trade_pnls = self._build_trade_pnls(trades, "net_pnl")

        if len(equity_series) < 2:
            return PerformanceMetrics()

        report = PerformanceMetricsCalculator.calculate(
            equity_series=equity_series,
            trade_pnls=trade_pnls,
        )
        return _report_to_metrics(report)

    def calculate_gross_net_report(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> GrossNetPerformanceReport:
        """Calculate side-by-side gross and net performance report."""
        from sqlalchemy import select
        portfolio = db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()

        initial_capital = portfolio.initial_capital if portfolio else Decimal("0.0000")

        gross_metrics = self.calculate_gross_performance(db, portfolio_id)
        net_metrics = self.calculate_net_performance(db, portfolio_id)

        # Current equity
        gross_series = self._build_equity_series(db, portfolio_id, "gross_equity")
        net_series = self._build_equity_series(db, portfolio_id, "net_equity")
        current_gross = Decimal(str(gross_series[-1])) if gross_series else initial_capital
        current_net = Decimal(str(net_series[-1])) if net_series else initial_capital
        total_costs = current_gross - current_net

        return GrossNetPerformanceReport(
            portfolio_id=portfolio_id,
            calculation_timestamp=datetime.now(UTC),
            initial_capital=initial_capital,
            current_equity_gross=current_gross,
            current_equity_net=current_net,
            total_costs_incurred=total_costs,
            gross=gross_metrics,
            net=net_metrics,
        )

    def get_daily_returns(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> list[ReturnEntry]:
        """Get daily gross and net returns from equity snapshots."""
        from sqlalchemy import select
        stmt = (
            select(EquitySnapshot)
            .where(EquitySnapshot.portfolio_id == portfolio_id)
            .order_by(EquitySnapshot.timestamp)
        )
        snapshots = list(db.execute(stmt).scalars().all())
        return [
            ReturnEntry(
                period=s.timestamp.date().isoformat(),
                gross_return_pct=float(s.daily_gross_return_pct),
                net_return_pct=float(s.daily_net_return_pct),
            )
            for s in snapshots
        ]

    def get_monthly_returns(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> list[ReturnEntry]:
        """Aggregate monthly returns from equity snapshots."""
        from sqlalchemy import select
        stmt = (
            select(EquitySnapshot)
            .where(EquitySnapshot.portfolio_id == portfolio_id)
            .order_by(EquitySnapshot.timestamp)
        )
        snapshots = list(db.execute(stmt).scalars().all())

        monthly: dict[str, dict[str, float]] = {}
        for s in snapshots:
            key = s.timestamp.strftime("%Y-%m")
            if key not in monthly:
                monthly[key] = {"gross": 0.0, "net": 0.0}
            monthly[key]["gross"] += float(s.daily_gross_return_pct)
            monthly[key]["net"] += float(s.daily_net_return_pct)

        return [
            ReturnEntry(
                period=k,
                gross_return_pct=round(v["gross"], 4),
                net_return_pct=round(v["net"], 4),
            )
            for k, v in sorted(monthly.items())
        ]
