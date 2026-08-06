"""Equity Curve Engine — Time-series recording and querying for gross/net equity, drawdowns, and growth curves."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.domains.analytics.models import EquitySnapshot
from app.domains.analytics.schemas import (
    DrawdownCurvePoint,
    DrawdownCurveResponse,
    EquityCurvePoint,
    EquityCurveResponse,
)
from app.domains.platform.logging import get_structured_logger
from app.domains.trading.models import Portfolio

log = get_structured_logger(__name__)

DEC_4DP = Decimal("0.0001")
DEC_6DP = Decimal("0.000001")


def _q4(v: Decimal) -> Decimal:
    return v.quantize(DEC_4DP, rounding=ROUND_HALF_UP)


def _q6(v: Decimal) -> Decimal:
    return v.quantize(DEC_6DP, rounding=ROUND_HALF_UP)


class EquityCurveService:
    """Records and queries time-series equity snapshots for gross and net portfolio equity."""

    def record_snapshot(
        self,
        db: Session,
        *,
        portfolio_id: uuid.UUID,
        timestamp: datetime,
        gross_equity: Decimal,
        net_equity: Decimal,
        cash_balance: Decimal,
        invested_value: Decimal,
        cost_profile_version: str = "default",
    ) -> EquitySnapshot:
        """Record an equity curve data point with automatically computed drawdowns and daily returns."""
        # Compute drawdowns from peak
        gross_peak = self._get_peak(db, portfolio_id, "gross_equity")
        net_peak = self._get_peak(db, portfolio_id, "net_equity")

        gross_dd = _q4(((gross_peak - gross_equity) / gross_peak) * Decimal("100")) if gross_peak > 0 else Decimal("0.0000")
        net_dd = _q4(((net_peak - net_equity) / net_peak) * Decimal("100")) if net_peak > 0 else Decimal("0.0000")

        # Compute daily returns from previous snapshot
        prev = self._get_latest_snapshot(db, portfolio_id)
        if prev:
            daily_gross_ret = _q6(((gross_equity - prev.gross_equity) / prev.gross_equity) * Decimal("100")) if prev.gross_equity > 0 else Decimal("0.000000")
            daily_net_ret = _q6(((net_equity - prev.net_equity) / prev.net_equity) * Decimal("100")) if prev.net_equity > 0 else Decimal("0.000000")
        else:
            daily_gross_ret = Decimal("0.000000")
            daily_net_ret = Decimal("0.000000")

        snapshot = EquitySnapshot(
            portfolio_id=portfolio_id,
            timestamp=timestamp,
            gross_equity=_q4(gross_equity),
            net_equity=_q4(net_equity),
            cash_balance=_q4(cash_balance),
            invested_value=_q4(invested_value),
            gross_drawdown_pct=max(gross_dd, Decimal("0.0000")),
            net_drawdown_pct=max(net_dd, Decimal("0.0000")),
            daily_gross_return_pct=daily_gross_ret,
            daily_net_return_pct=daily_net_ret,
            cost_profile_version=cost_profile_version,
        )
        db.add(snapshot)
        db.flush()
        return snapshot

    def _get_peak(self, db: Session, portfolio_id: uuid.UUID, field: str) -> Decimal:
        """Get the historical peak equity value."""
        stmt = select(func.max(getattr(EquitySnapshot, field))).where(
            EquitySnapshot.portfolio_id == portfolio_id
        )
        result = db.execute(stmt).scalar()
        return Decimal(str(result)) if result else Decimal("0.0000")

    def _get_latest_snapshot(self, db: Session, portfolio_id: uuid.UUID) -> EquitySnapshot | None:
        """Get the most recent equity snapshot."""
        stmt = (
            select(EquitySnapshot)
            .where(EquitySnapshot.portfolio_id == portfolio_id)
            .order_by(EquitySnapshot.timestamp.desc())
            .limit(1)
        )
        return db.execute(stmt).scalar_one_or_none()

    def get_equity_curve(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> EquityCurveResponse:
        """Get gross and net equity curve time-series."""
        stmt = select(EquitySnapshot).where(
            EquitySnapshot.portfolio_id == portfolio_id
        )
        if start:
            stmt = stmt.where(EquitySnapshot.timestamp >= start)
        if end:
            stmt = stmt.where(EquitySnapshot.timestamp <= end)
        stmt = stmt.order_by(EquitySnapshot.timestamp)

        snapshots = list(db.execute(stmt).scalars().all())
        portfolio = db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()
        initial_capital = portfolio.initial_capital if portfolio else Decimal("0.0000")

        points = [
            EquityCurvePoint(
                timestamp=s.timestamp,
                gross_equity=s.gross_equity,
                net_equity=s.net_equity,
                cash_balance=s.cash_balance,
                invested_value=s.invested_value,
            )
            for s in snapshots
        ]

        gross_ret = 0.0
        net_ret = 0.0
        if snapshots and float(initial_capital) > 0:
            gross_ret = round(((float(snapshots[-1].gross_equity) - float(initial_capital)) / float(initial_capital)) * 100, 4)
            net_ret = round(((float(snapshots[-1].net_equity) - float(initial_capital)) / float(initial_capital)) * 100, 4)

        return EquityCurveResponse(
            portfolio_id=portfolio_id,
            points=points,
            initial_capital=initial_capital,
            gross_total_return_pct=gross_ret,
            net_total_return_pct=net_ret,
        )

    def get_drawdown_curve(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> DrawdownCurveResponse:
        """Get drawdown curve time-series."""
        stmt = (
            select(EquitySnapshot)
            .where(EquitySnapshot.portfolio_id == portfolio_id)
            .order_by(EquitySnapshot.timestamp)
        )
        snapshots = list(db.execute(stmt).scalars().all())

        points = [
            DrawdownCurvePoint(
                timestamp=s.timestamp,
                gross_drawdown_pct=s.gross_drawdown_pct,
                net_drawdown_pct=s.net_drawdown_pct,
            )
            for s in snapshots
        ]

        max_gross_dd = max((float(s.gross_drawdown_pct) for s in snapshots), default=0.0)
        max_net_dd = max((float(s.net_drawdown_pct) for s in snapshots), default=0.0)

        return DrawdownCurveResponse(
            portfolio_id=portfolio_id,
            points=points,
            max_gross_drawdown_pct=round(max_gross_dd, 4),
            max_net_drawdown_pct=round(max_net_dd, 4),
        )
