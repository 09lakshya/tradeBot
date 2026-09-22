"""Alert Engine — Threshold-based operational alerts for portfolio risk monitoring."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.domains.analytics.enums import AlertSeverity, AlertType
from app.domains.analytics.models import AnalyticsAlert, EquitySnapshot, TradeJournalEntry
from app.domains.platform.logging import get_structured_logger
from app.domains.trading.enums import PositionStatus
from app.domains.trading.models import Portfolio, Position

log = get_structured_logger(__name__)


class AlertEngine:
    """Evaluates configurable alert rules and persists triggered alerts."""

    def __init__(
        self,
        *,
        drawdown_threshold_pct: float = 10.0,
        losing_streak_threshold: int = 5,
        high_exposure_threshold_pct: float = 25.0,
        low_win_rate_threshold_pct: float = 40.0,
        slippage_threshold_bps: float = 10.0,
        high_costs_threshold_pct: float = 2.0,
        min_capital_util_pct: float = 20.0,
        max_capital_util_pct: float = 90.0,
        max_single_position_pct: float = 30.0,
    ) -> None:
        self.drawdown_threshold_pct = drawdown_threshold_pct
        self.losing_streak_threshold = losing_streak_threshold
        self.high_exposure_threshold_pct = high_exposure_threshold_pct
        self.low_win_rate_threshold_pct = low_win_rate_threshold_pct
        self.slippage_threshold_bps = slippage_threshold_bps
        self.high_costs_threshold_pct = high_costs_threshold_pct
        self.min_capital_util_pct = min_capital_util_pct
        self.max_capital_util_pct = max_capital_util_pct
        self.max_single_position_pct = max_single_position_pct

    def evaluate_alerts(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> list[AnalyticsAlert]:
        """Run all alert rules and persist triggered alerts."""
        alerts: list[AnalyticsAlert] = []

        alerts.extend(self._check_drawdown(db, portfolio_id))
        alerts.extend(self._check_losing_streak(db, portfolio_id))
        alerts.extend(self._check_low_win_rate(db, portfolio_id))
        alerts.extend(self._check_capital_utilization(db, portfolio_id))
        alerts.extend(self._check_portfolio_imbalance(db, portfolio_id))
        alerts.extend(self._check_high_costs(db, portfolio_id))

        for alert in alerts:
            db.add(alert)
        if alerts:
            db.flush()

        log.info("alerts_evaluated", portfolio_id=str(portfolio_id), triggered=len(alerts))
        return alerts

    def get_active_alerts(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> list[AnalyticsAlert]:
        """Get all unacknowledged alerts."""
        stmt = (
            select(AnalyticsAlert)
            .where(and_(
                AnalyticsAlert.portfolio_id == portfolio_id,
                AnalyticsAlert.is_acknowledged.is_(False),
            ))
            .order_by(AnalyticsAlert.created_at.desc())
        )
        return list(db.execute(stmt).scalars().all())

    def acknowledge_alert(self, db: Session, alert_id: uuid.UUID) -> bool:
        """Mark an alert as acknowledged."""
        stmt = select(AnalyticsAlert).where(AnalyticsAlert.id == alert_id)
        alert = db.execute(stmt).scalar_one_or_none()
        if alert:
            alert.is_acknowledged = True
            db.flush()
            return True
        return False

    def _check_drawdown(self, db: Session, portfolio_id: uuid.UUID) -> list[AnalyticsAlert]:
        """Check for large drawdown."""
        stmt = (
            select(EquitySnapshot)
            .where(EquitySnapshot.portfolio_id == portfolio_id)
            .order_by(EquitySnapshot.timestamp.desc())
            .limit(1)
        )
        latest = db.execute(stmt).scalar_one_or_none()
        if not latest:
            return []

        dd = float(latest.net_drawdown_pct)
        if dd >= self.drawdown_threshold_pct:
            return [AnalyticsAlert(
                portfolio_id=portfolio_id,
                alert_type=AlertType.large_drawdown,
                severity=AlertSeverity.critical if dd >= self.drawdown_threshold_pct * 2 else AlertSeverity.warning,
                title=f"Large Drawdown: {dd:.2f}%",
                message=f"Portfolio drawdown has reached {dd:.2f}%, exceeding the {self.drawdown_threshold_pct}% threshold.",
                metric_name="net_drawdown_pct",
                metric_value=Decimal(str(round(dd, 4))),
                threshold_value=Decimal(str(self.drawdown_threshold_pct)),
            )]
        return []

    def _check_losing_streak(self, db: Session, portfolio_id: uuid.UUID) -> list[AnalyticsAlert]:
        """Check for consecutive losing trades."""
        stmt = (
            select(TradeJournalEntry)
            .where(TradeJournalEntry.portfolio_id == portfolio_id)
            .order_by(TradeJournalEntry.exit_timestamp.desc())
            .limit(self.losing_streak_threshold + 5)
        )
        trades = list(db.execute(stmt).scalars().all())

        streak = 0
        for t in trades:
            if t.net_pnl < 0:
                streak += 1
            else:
                break

        if streak >= self.losing_streak_threshold:
            return [AnalyticsAlert(
                portfolio_id=portfolio_id,
                alert_type=AlertType.losing_streak,
                severity=AlertSeverity.warning,
                title=f"Losing Streak: {streak} consecutive losses",
                message=f"The portfolio has {streak} consecutive losing trades.",
                metric_name="consecutive_losses",
                metric_value=Decimal(str(streak)),
                threshold_value=Decimal(str(self.losing_streak_threshold)),
            )]
        return []

    def _check_low_win_rate(self, db: Session, portfolio_id: uuid.UUID) -> list[AnalyticsAlert]:
        """Check for low win rate over recent trades."""
        stmt = (
            select(TradeJournalEntry)
            .where(TradeJournalEntry.portfolio_id == portfolio_id)
            .order_by(TradeJournalEntry.exit_timestamp.desc())
            .limit(50)
        )
        trades = list(db.execute(stmt).scalars().all())
        if len(trades) < 10:
            return []

        wins = len([t for t in trades if t.net_pnl > 0])
        win_rate = wins / len(trades) * 100

        if win_rate < self.low_win_rate_threshold_pct:
            return [AnalyticsAlert(
                portfolio_id=portfolio_id,
                alert_type=AlertType.low_win_rate,
                severity=AlertSeverity.warning,
                title=f"Low Win Rate: {win_rate:.1f}%",
                message=f"Win rate over last {len(trades)} trades is {win_rate:.1f}%, below {self.low_win_rate_threshold_pct}%.",
                metric_name="win_rate_pct",
                metric_value=Decimal(str(round(win_rate, 2))),
                threshold_value=Decimal(str(self.low_win_rate_threshold_pct)),
            )]
        return []

    def _check_capital_utilization(self, db: Session, portfolio_id: uuid.UUID) -> list[AnalyticsAlert]:
        """Check if capital utilization is outside healthy bounds."""
        portfolio = db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()
        if not portfolio:
            return []

        positions = list(db.execute(
            select(Position).where(
                Position.portfolio_id == portfolio_id,
                Position.status == PositionStatus.open,
            )
        ).scalars().all())

        invested = sum(p.quantity * p.current_price for p in positions)
        total = portfolio.cash_balance + portfolio.reserved_cash + invested
        util = float(invested / total * 100) if total > 0 else 0.0

        alerts = []
        if util > self.max_capital_util_pct:
            alerts.append(AnalyticsAlert(
                portfolio_id=portfolio_id,
                alert_type=AlertType.capital_utilization,
                severity=AlertSeverity.warning,
                title=f"High Capital Utilization: {util:.1f}%",
                message=f"Capital utilization at {util:.1f}%, exceeding max threshold of {self.max_capital_util_pct}%.",
                metric_name="capital_utilization_pct",
                metric_value=Decimal(str(round(util, 2))),
                threshold_value=Decimal(str(self.max_capital_util_pct)),
            ))
        return alerts

    def _check_portfolio_imbalance(self, db: Session, portfolio_id: uuid.UUID) -> list[AnalyticsAlert]:
        """Check if any single position exceeds concentration limits."""
        portfolio = db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()
        if not portfolio:
            return []

        positions = list(db.execute(
            select(Position).where(
                Position.portfolio_id == portfolio_id,
                Position.status == PositionStatus.open,
            )
        ).scalars().all())

        invested = sum(p.quantity * p.current_price for p in positions)
        total = portfolio.cash_balance + portfolio.reserved_cash + invested

        alerts = []
        for pos in positions:
            mv = pos.quantity * pos.current_price
            pct = float(mv / total * 100) if total > 0 else 0.0
            if pct > self.max_single_position_pct:
                alerts.append(AnalyticsAlert(
                    portfolio_id=portfolio_id,
                    alert_type=AlertType.portfolio_imbalance,
                    severity=AlertSeverity.warning,
                    title=f"Position Concentration: {pct:.1f}%",
                    message=f"Single position at {pct:.1f}% of portfolio, exceeding {self.max_single_position_pct}% limit.",
                    metric_name="single_position_pct",
                    metric_value=Decimal(str(round(pct, 2))),
                    threshold_value=Decimal(str(self.max_single_position_pct)),
                ))
        return alerts

    def _check_high_costs(self, db: Session, portfolio_id: uuid.UUID) -> list[AnalyticsAlert]:
        """Check if trading costs as a percentage of turnover are excessive."""
        stmt = (
            select(TradeJournalEntry)
            .where(TradeJournalEntry.portfolio_id == portfolio_id)
            .order_by(TradeJournalEntry.exit_timestamp.desc())
            .limit(50)
        )
        trades = list(db.execute(stmt).scalars().all())
        if not trades:
            return []

        total_turnover = sum(t.entry_price * t.quantity for t in trades)
        total_costs = sum(Decimal(str(t.cost_breakdown.get("total_charges", "0"))) for t in trades)
        cost_pct = float(total_costs / total_turnover * 100) if total_turnover > 0 else 0.0

        if cost_pct > self.high_costs_threshold_pct:
            return [AnalyticsAlert(
                portfolio_id=portfolio_id,
                alert_type=AlertType.high_costs,
                severity=AlertSeverity.info,
                title=f"High Trading Costs: {cost_pct:.2f}%",
                message=f"Trading costs are {cost_pct:.2f}% of turnover, exceeding {self.high_costs_threshold_pct}%.",
                metric_name="cost_pct_of_turnover",
                metric_value=Decimal(str(round(cost_pct, 4))),
                threshold_value=Decimal(str(self.high_costs_threshold_pct)),
            )]
        return []
