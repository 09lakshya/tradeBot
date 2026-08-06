"""Integration tests for Analytics Domain."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.domains.analytics.alerts import AlertEngine
from app.domains.analytics.attribution import StrategyAttributionService
from app.domains.analytics.cost_profiles import CostProfileManager
from app.domains.analytics.equity_curve import EquityCurveService
from app.domains.analytics.performance import PerformanceAnalyticsService
from app.domains.analytics.regime import MarketRegimeAnalyzer
from app.domains.analytics.reports import ReportGeneratorService
from app.domains.analytics.schemas import TradeJournalFilterRequest
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.market_data.enums import Exchange
from app.domains.trading.enums import OrderSide, ProductType
from app.domains.trading.models import Portfolio


@pytest.fixture
def portfolio(db):
    p = Portfolio(name="Analytics Integration Test", initial_capital=Decimal("100000.0000"), cash_balance=Decimal("100000.0000"))
    db.add(p)
    db.flush()
    return p


def test_full_analytics_lifecycle_integration(db, portfolio):
    """End-to-End integration flow:
    1. Record trades via TradeJournalService with cost breakdown from CostProfileManager
    2. Record time-series equity snapshots via EquityCurveService
    3. Generate side-by-side Gross vs Net performance report via PerformanceAnalyticsService
    4. Compute strategy attribution & leaderboard via StrategyAttributionService
    5. Classify and aggregate market regime performance via MarketRegimeAnalyzer
    6. Generate daily report via ReportGeneratorService
    7. Evaluate alerts via AlertEngine
    """
    journal = TradeJournalService()
    cost_mgr = CostProfileManager()
    equity_svc = EquityCurveService()
    perf_svc = PerformanceAnalyticsService()
    attr_svc = StrategyAttributionService()
    regime_svc = MarketRegimeAnalyzer()
    report_svc = ReportGeneratorService()
    alert_engine = AlertEngine()

    now = datetime.now(timezone.utc)
    inst1, inst2 = uuid.uuid4(), uuid.uuid4()

    # Step 1: Calculate trade costs using Zerodha profile
    cost1 = cost_mgr.calculate_trade_costs(
        side=OrderSide.buy, product_type=ProductType.cnc, exchange=Exchange.NSE,
        quantity=Decimal("50.0000"), price=Decimal("2000.0000"), profile_name="zerodha_2026_v1",
    )
    cost2 = cost_mgr.calculate_trade_costs(
        side=OrderSide.buy, product_type=ProductType.cnc, exchange=Exchange.NSE,
        quantity=Decimal("100.0000"), price=Decimal("500.0000"), profile_name="zerodha_2026_v1",
    )

    # Step 2: Record completed trades
    t1 = journal.record_trade(
        db, portfolio_id=portfolio.id, instrument_id=inst1,
        strategy_id="trend_alpha", symbol="RELIANCE", sector="Energy",
        entry_timestamp=now - timedelta(days=5), exit_timestamp=now - timedelta(days=4),
        entry_price=Decimal("2000.0000"), exit_price=Decimal("2100.0000"),
        quantity=Decimal("50.0000"), cost_breakdown=cost1.model_dump(mode="json"),
        cost_profile_version="zerodha_2026_v1", market_regime="trending_bullish",
    )
    assert t1.gross_pnl == Decimal("5000.0000")

    t2 = journal.record_trade(
        db, portfolio_id=portfolio.id, instrument_id=inst2,
        strategy_id="mean_reversion_beta", symbol="TCS", sector="IT",
        entry_timestamp=now - timedelta(days=3), exit_timestamp=now - timedelta(days=2),
        entry_price=Decimal("500.0000"), exit_price=Decimal("480.0000"),
        quantity=Decimal("100.0000"), cost_breakdown=cost2.model_dump(mode="json"),
        cost_profile_version="zerodha_2026_v1", market_regime="ranging",
    )
    assert t2.gross_pnl == Decimal("-2000.0000")

    # Step 3: Record equity snapshots
    equity_svc.record_snapshot(
        db, portfolio_id=portfolio.id, timestamp=now - timedelta(days=5),
        gross_equity=Decimal("100000.0000"), net_equity=Decimal("100000.0000"),
        cash_balance=Decimal("100000.0000"), invested_value=Decimal("0.0000"),
    )
    equity_svc.record_snapshot(
        db, portfolio_id=portfolio.id, timestamp=now - timedelta(days=3),
        gross_equity=Decimal("105000.0000"), net_equity=Decimal("104850.0000"),
        cash_balance=Decimal("105000.0000"), invested_value=Decimal("0.0000"),
    )
    equity_svc.record_snapshot(
        db, portfolio_id=portfolio.id, timestamp=now,
        gross_equity=Decimal("103000.0000"), net_equity=Decimal("102700.0000"),
        cash_balance=Decimal("103000.0000"), invested_value=Decimal("0.0000"),
    )

    # Step 4: Gross vs Net performance report
    perf_report = perf_svc.calculate_gross_net_report(db, portfolio.id)
    assert perf_report.current_equity_gross == Decimal("103000.0000")
    assert perf_report.current_equity_net == Decimal("102700.0000")

    # Step 5: Strategy Attribution
    attributions = attr_svc.get_all_strategy_attributions(db, portfolio.id)
    assert len(attributions) == 2

    leaderboard = attr_svc.get_strategy_leaderboard(db, portfolio.id)
    assert len(leaderboard) == 2
    assert leaderboard[0].strategy_id == "trend_alpha"

    # Step 6: Market Regime Statistics
    regime_stats = regime_svc.get_regime_statistics(db, portfolio.id)
    assert len(regime_stats.regime_stats) == 2

    # Step 7: Report Generation
    daily_report = report_svc.generate_daily_report(db, portfolio.id, now.date())
    assert daily_report.portfolio_id == portfolio.id

    # Step 8: Alerts
    alerts = alert_engine.evaluate_alerts(db, portfolio.id)
    assert isinstance(alerts, list)
