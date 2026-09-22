"""Report Generator Engine — Automated daily, weekly, and monthly performance reports."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.domains.analytics.attribution import StrategyAttributionService
from app.domains.analytics.enums import ReportPeriod
from app.domains.analytics.models import EquitySnapshot, TradeJournalEntry
from app.domains.analytics.schemas import (
    DetailedCostBreakdown,
    PeriodReportResponse,
    TradeSummary,
)
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.platform.logging import get_structured_logger
from app.domains.trading.models import Portfolio

log = get_structured_logger(__name__)


class ReportGeneratorService:
    """Generates automated daily, weekly, and monthly performance reports."""

    def __init__(self) -> None:
        self._journal = TradeJournalService()
        self._attribution = StrategyAttributionService()

    def generate_daily_report(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        report_date: date,
    ) -> PeriodReportResponse:
        """Generate a daily performance report."""
        start = datetime.combine(report_date, datetime.min.time()).replace(tzinfo=UTC)
        end = start + timedelta(days=1)
        return self._generate_report(db, portfolio_id, str(report_date), ReportPeriod.daily, start, end)

    def generate_weekly_report(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        week_start: date,
    ) -> PeriodReportResponse:
        """Generate a weekly performance report."""
        start = datetime.combine(week_start, datetime.min.time()).replace(tzinfo=UTC)
        end = start + timedelta(days=7)
        period_label = f"{week_start} to {week_start + timedelta(days=6)}"
        return self._generate_report(db, portfolio_id, period_label, ReportPeriod.weekly, start, end)

    def generate_monthly_report(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        year: int,
        month: int,
    ) -> PeriodReportResponse:
        """Generate a monthly performance report."""
        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)
        period_label = f"{year}-{month:02d}"
        return self._generate_report(db, portfolio_id, period_label, ReportPeriod.monthly, start, end)

    def _generate_report(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        period_label: str,
        period_type: ReportPeriod,
        start: datetime,
        end: datetime,
    ) -> PeriodReportResponse:
        """Core report generation logic."""
        portfolio = db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()

        # Trades in period
        stmt = (
            select(TradeJournalEntry)
            .where(and_(
                TradeJournalEntry.portfolio_id == portfolio_id,
                TradeJournalEntry.exit_timestamp >= start,
                TradeJournalEntry.exit_timestamp < end,
            ))
            .order_by(TradeJournalEntry.exit_timestamp)
        )
        trades = list(db.execute(stmt).scalars().all())

        # Trade summary
        trade_summary = self._build_trade_summary(trades)

        # P&L
        gross_pnl = sum(t.gross_pnl for t in trades)
        net_pnl = sum(t.net_pnl for t in trades)
        initial = portfolio.initial_capital if portfolio else Decimal("1.0000")
        gross_return_pct = round(float(gross_pnl / initial * 100), 4) if initial > 0 else 0.0
        net_return_pct = round(float(net_pnl / initial * 100), 4) if initial > 0 else 0.0

        # Cost analysis
        cost_analysis = self._aggregate_costs(trades)

        # Strategy rankings
        strategy_pnl: dict[str, Decimal] = {}
        for t in trades:
            strategy_pnl[t.strategy_id] = strategy_pnl.get(t.strategy_id, Decimal("0")) + t.net_pnl
        sorted_strats = sorted(strategy_pnl.items(), key=lambda x: x[1], reverse=True)
        best_strategy = sorted_strats[0][0] if sorted_strats else None
        worst_strategy = sorted_strats[-1][0] if sorted_strats else None

        # Drawdown
        equity_stmt = (
            select(EquitySnapshot)
            .where(and_(
                EquitySnapshot.portfolio_id == portfolio_id,
                EquitySnapshot.timestamp >= start,
                EquitySnapshot.timestamp < end,
            ))
        )
        snapshots = list(db.execute(equity_stmt).scalars().all())
        largest_dd = max((float(s.net_drawdown_pct) for s in snapshots), default=0.0)

        # Portfolio summary
        portfolio_summary: dict[str, Any] = {}
        if portfolio:
            portfolio_summary = {
                "name": portfolio.name,
                "initial_capital": str(portfolio.initial_capital),
                "cash_balance": str(portfolio.cash_balance),
            }

        return PeriodReportResponse(
            portfolio_id=portfolio_id,
            period=period_label,
            period_type=period_type,
            generated_at=datetime.now(UTC),
            portfolio_summary=portfolio_summary,
            gross_return_pct=gross_return_pct,
            net_return_pct=net_return_pct,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            trade_summary=trade_summary,
            best_strategy=best_strategy,
            worst_strategy=worst_strategy,
            largest_drawdown_pct=round(largest_dd, 4),
            cost_analysis=cost_analysis,
        )

    @staticmethod
    def _build_trade_summary(trades: list[TradeJournalEntry]) -> TradeSummary:
        """Build trade summary from journal entries."""
        if not trades:
            return TradeSummary()

        winners = [t for t in trades if t.net_pnl > 0]
        losers = [t for t in trades if t.net_pnl <= 0]
        best = max(trades, key=lambda t: t.net_pnl)
        worst = min(trades, key=lambda t: t.net_pnl)

        return TradeSummary(
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            best_trade_pnl=best.net_pnl,
            best_trade_symbol=best.symbol,
            worst_trade_pnl=worst.net_pnl,
            worst_trade_symbol=worst.symbol,
        )

    @staticmethod
    def _aggregate_costs(trades: list[TradeJournalEntry]) -> DetailedCostBreakdown:
        """Aggregate cost breakdowns from all trades in a period."""
        totals = DetailedCostBreakdown()
        for t in trades:
            cb = t.cost_breakdown or {}
            totals.brokerage += Decimal(str(cb.get("brokerage", "0")))
            totals.stt += Decimal(str(cb.get("stt", "0")))
            totals.exchange_charges += Decimal(str(cb.get("exchange_charges", "0")))
            totals.gst += Decimal(str(cb.get("gst", "0")))
            totals.stamp_duty += Decimal(str(cb.get("stamp_duty", "0")))
            totals.sebi_charges += Decimal(str(cb.get("sebi_charges", "0")))
            totals.total_charges += Decimal(str(cb.get("total_charges", "0")))
        return totals
