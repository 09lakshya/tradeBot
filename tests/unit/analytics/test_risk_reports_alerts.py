"""Unit tests for Risk Analytics, Report Generator, and Alert Engine."""
import uuid
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

import pytest
from app.domains.analytics.alerts import AlertEngine
from app.domains.analytics.enums import AlertType
from app.domains.analytics.equity_curve import EquityCurveService
from app.domains.analytics.reports import ReportGeneratorService
from app.domains.analytics.risk_analytics import PortfolioRiskAnalyticsService
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.trading.enums import PositionStatus, ProductType
from app.domains.trading.models import Portfolio, Position


@pytest.fixture
def portfolio(db):
    p = Portfolio(name="Risk Test", initial_capital=Decimal("100000.0000"), cash_balance=Decimal("60000.0000"))
    db.add(p)
    db.flush()
    return p


def test_portfolio_risk_analytics(db, portfolio):
    risk_service = PortfolioRiskAnalyticsService()
    inst_id = uuid.uuid4()

    pos = Position(
        portfolio_id=portfolio.id,
        instrument_id=inst_id,
        product_type=ProductType.cnc,
        quantity=Decimal("100.0000"),
        avg_entry_price=Decimal("400.0000"),
        current_price=Decimal("400.0000"),
        status=PositionStatus.open,
    )
    db.add(pos)
    db.flush()

    sector_map = {inst_id: "IT"}
    analytics = risk_service.get_portfolio_risk_analytics(
        db, portfolio.id, sector_mappings=sector_map
    )

    assert analytics.portfolio_id == portfolio.id
    assert len(analytics.sector_exposure) == 1
    assert analytics.sector_exposure[0].name == "IT"
    assert analytics.cash_utilization_pct == 40.0  # 40k invested / 100k total
    assert analytics.position_count == 1


def test_report_generator_service(db, portfolio):
    report_service = ReportGeneratorService()
    journal = TradeJournalService()
    now = datetime.now(timezone.utc)
    inst_id = uuid.uuid4()

    journal.record_trade(
        db, portfolio_id=portfolio.id, instrument_id=inst_id,
        strategy_id="strat_daily", symbol="AXISBANK",
        entry_timestamp=now, exit_timestamp=now,
        entry_price=Decimal("900.0000"), exit_price=Decimal("950.0000"),
        quantity=Decimal("10.0000"), cost_breakdown={"total_charges": "25.00"},
    )

    report = report_service.generate_daily_report(db, portfolio.id, now.date())
    assert report.portfolio_id == portfolio.id
    assert report.trade_summary.total_trades == 1
    assert report.gross_pnl == Decimal("500.0000")
    assert report.net_pnl == Decimal("475.0000")
    assert report.best_strategy == "strat_daily"


def test_alert_engine_evaluation(db, portfolio):
    alert_engine = AlertEngine(drawdown_threshold_pct=5.0, losing_streak_threshold=3)
    eq_service = EquityCurveService()
    journal = TradeJournalService()
    now = datetime.now(timezone.utc)
    inst_id = uuid.uuid4()

    # Create a 10% drawdown
    eq_service.record_snapshot(
        db, portfolio_id=portfolio.id, timestamp=now - timedelta(days=1),
        gross_equity=Decimal("100000.0000"), net_equity=Decimal("100000.0000"),
        cash_balance=Decimal("100000.0000"), invested_value=Decimal("0.0000"),
    )
    eq_service.record_snapshot(
        db, portfolio_id=portfolio.id, timestamp=now,
        gross_equity=Decimal("90000.0000"), net_equity=Decimal("90000.0000"),
        cash_balance=Decimal("90000.0000"), invested_value=Decimal("0.0000"),
    )

    # Create 3 losing trades
    for i in range(3):
        journal.record_trade(
            db, portfolio_id=portfolio.id, instrument_id=inst_id,
            strategy_id="s1", symbol="LTI",
            entry_timestamp=now, exit_timestamp=now,
            entry_price=Decimal("5000.0000"), exit_price=Decimal("4800.0000"),
            quantity=Decimal("2.0000"),
        )

    alerts = alert_engine.evaluate_alerts(db, portfolio.id)
    assert len(alerts) >= 2

    active = alert_engine.get_active_alerts(db, portfolio.id)
    assert len(active) >= 2

    # Acknowledge alert
    success = alert_engine.acknowledge_alert(db, active[0].id)
    assert success is True
    assert len(alert_engine.get_active_alerts(db, portfolio.id)) == len(active) - 1
