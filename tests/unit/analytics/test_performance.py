"""Unit tests for Performance Analytics and Equity Curve Engine."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.domains.analytics.equity_curve import EquityCurveService
from app.domains.analytics.performance import PerformanceAnalyticsService
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.trading.models import Portfolio


@pytest.fixture
def portfolio(db):
    p = Portfolio(name="Perf Test", initial_capital=Decimal("100000.0000"), cash_balance=Decimal("100000.0000"))
    db.add(p)
    db.flush()
    return p


def test_equity_curve_recording_and_retrieval(db, portfolio):
    eq_service = EquityCurveService()
    now = datetime.now(timezone.utc)

    # Day 1
    eq_service.record_snapshot(
        db,
        portfolio_id=portfolio.id,
        timestamp=now - timedelta(days=2),
        gross_equity=Decimal("100000.0000"),
        net_equity=Decimal("100000.0000"),
        cash_balance=Decimal("100000.0000"),
        invested_value=Decimal("0.0000"),
    )

    # Day 2
    eq_service.record_snapshot(
        db,
        portfolio_id=portfolio.id,
        timestamp=now - timedelta(days=1),
        gross_equity=Decimal("105000.0000"),
        net_equity=Decimal("104800.0000"),
        cash_balance=Decimal("50000.0000"),
        invested_value=Decimal("55000.0000"),
    )

    # Day 3
    eq_service.record_snapshot(
        db,
        portfolio_id=portfolio.id,
        timestamp=now,
        gross_equity=Decimal("110000.0000"),
        net_equity=Decimal("109500.0000"),
        cash_balance=Decimal("110000.0000"),
        invested_value=Decimal("0.0000"),
    )

    curve = eq_service.get_equity_curve(db, portfolio.id)
    assert len(curve.points) == 3
    assert curve.gross_total_return_pct == 10.0  # (110k-100k)/100k
    assert curve.net_total_return_pct == 9.5     # (109.5k-100k)/100k

    dd = eq_service.get_drawdown_curve(db, portfolio.id)
    assert len(dd.points) == 3
    assert dd.max_gross_drawdown_pct == 0.0


def test_gross_vs_net_performance_report(db, portfolio):
    eq_service = EquityCurveService()
    perf_service = PerformanceAnalyticsService()
    journal_service = TradeJournalService()
    now = datetime.now(timezone.utc)
    inst_id = uuid.uuid4()

    # Record equity snapshots
    for i in range(10):
        t = now - timedelta(days=10 - i)
        gross = Decimal("100000.0000") + Decimal(str(i * 1000))
        net = Decimal("100000.0000") + Decimal(str(i * 950))
        eq_service.record_snapshot(
            db, portfolio_id=portfolio.id, timestamp=t,
            gross_equity=gross, net_equity=net,
            cash_balance=gross, invested_value=Decimal("0.0000"),
        )

    # Record trade
    journal_service.record_trade(
        db,
        portfolio_id=portfolio.id,
        instrument_id=inst_id,
        strategy_id="trend_v1",
        symbol="TATASTEEL",
        entry_timestamp=now - timedelta(days=5),
        exit_timestamp=now - timedelta(days=4),
        entry_price=Decimal("100.0000"),
        exit_price=Decimal("110.0000"),
        quantity=Decimal("500.0000"),
        cost_breakdown={"total_charges": "250.00"},
    )

    report = perf_service.calculate_gross_net_report(db, portfolio.id)
    assert report.portfolio_id == portfolio.id
    assert report.total_costs_incurred == Decimal("450.0000")
    assert report.gross.total_trades == 1
    assert report.net.total_trades == 1
