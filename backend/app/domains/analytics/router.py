"""REST API endpoints for Analytics, Trade Journal, Performance, and Paper Trading Dashboard."""
from __future__ import annotations

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.analytics.alerts import AlertEngine
from app.domains.analytics.attribution import StrategyAttributionService
from app.domains.analytics.benchmark import BenchmarkComparisonService
from app.domains.analytics.cost_profiles import CostProfileManager
from app.domains.analytics.deps import (
    get_alert_engine,
    get_attribution_service,
    get_benchmark_service,
    get_cost_profile_manager,
    get_equity_curve_service,
    get_performance_analytics_service,
    get_regime_analyzer,
    get_report_generator_service,
    get_risk_analytics_service,
    get_trade_journal_service,
    get_validation_service,
    get_version_tracker,
)
from app.domains.analytics.equity_curve import EquityCurveService
from app.domains.analytics.models import AnalyticsAlert, TradeJournalEntry
from app.domains.analytics.performance import PerformanceAnalyticsService
from app.domains.analytics.regime import MarketRegimeAnalyzer
from app.domains.analytics.reports import ReportGeneratorService
from app.domains.analytics.risk_analytics import PortfolioRiskAnalyticsService
from app.domains.analytics.schemas import (
    AlertAcknowledgeRequest,
    AlertResponse,
    BenchmarkComparisonRequest,
    BenchmarkComparisonResponse,
    CostComparisonResponse,
    CostProfileCreateRequest,
    CostProfileResponse,
    DrawdownCurveResponse,
    EquityCurveResponse,
    GrossNetPerformanceReport,
    MonteCarloAnalysisResponse,
    MonteCarloRequest,
    PaperTradingDashboardResponse,
    PeriodReportResponse,
    PortfolioRiskAnalytics,
    RegimeStatisticsResponse,
    StrategyAttributionReport,
    StrategyLeaderboardEntry,
    StrategyVersionComparisonResponse,
    TradeJournalEntryResponse,
    TradeJournalExportResponse,
    TradeJournalFilterRequest,
    WalkForwardAnalysisResponse,
    WalkForwardRequest,
)
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.analytics.validation import ValidationService
from app.domains.analytics.version_tracker import StrategyVersionTracker
from app.domains.trading.models import Portfolio, Position

router = APIRouter()


# ── Trade Journal ──────────────────────────────────────────────────────────────


@router.post("/journal", response_model=list[TradeJournalEntryResponse])
def get_trade_journal(
    filters: TradeJournalFilterRequest,
    db: Session = Depends(get_db),
    journal_service: TradeJournalService = Depends(get_trade_journal_service),
) -> list[TradeJournalEntryResponse]:
    """Query trade journal entries with optional filtering by strategy, symbol, regime, and date range."""
    entries = journal_service.get_trades(db, filters)
    return [TradeJournalEntryResponse.model_validate(e) for e in entries]


@router.get("/journal/{trade_id}", response_model=TradeJournalEntryResponse)
def get_trade_by_id(
    trade_id: str,
    db: Session = Depends(get_db),
    journal_service: TradeJournalService = Depends(get_trade_journal_service),
) -> TradeJournalEntryResponse:
    """Fetch a single trade journal entry by trade ID."""
    entry = journal_service.get_trade_by_id(db, trade_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    return TradeJournalEntryResponse.model_validate(entry)


@router.post("/journal/export", response_model=TradeJournalExportResponse)
def export_trade_journal(
    portfolio_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: Session = Depends(get_db),
    journal_service: TradeJournalService = Depends(get_trade_journal_service),
) -> TradeJournalExportResponse:
    """Export complete trade journal data for a portfolio."""
    return journal_service.export_trades(db, portfolio_id, start_date, end_date)


# ── Performance Analytics ──────────────────────────────────────────────────────


@router.get("/performance/{portfolio_id}", response_model=GrossNetPerformanceReport)
def get_performance_report(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    perf_service: PerformanceAnalyticsService = Depends(get_performance_analytics_service),
) -> GrossNetPerformanceReport:
    """Get side-by-side Gross vs Net performance analytics."""
    return perf_service.calculate_gross_net_report(db, portfolio_id)


# ── Equity Curve & Drawdown ───────────────────────────────────────────────────


@router.get("/equity-curve/{portfolio_id}", response_model=EquityCurveResponse)
def get_equity_curve(
    portfolio_id: uuid.UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    equity_service: EquityCurveService = Depends(get_equity_curve_service),
) -> EquityCurveResponse:
    """Get gross and net equity curve time-series data."""
    return equity_service.get_equity_curve(db, portfolio_id, start, end)


@router.get("/drawdown/{portfolio_id}", response_model=DrawdownCurveResponse)
def get_drawdown_curve(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    equity_service: EquityCurveService = Depends(get_equity_curve_service),
) -> DrawdownCurveResponse:
    """Get drawdown curve time-series data."""
    return equity_service.get_drawdown_curve(db, portfolio_id)


# ── Strategy Attribution ───────────────────────────────────────────────────────


@router.get("/attribution/{portfolio_id}", response_model=list[StrategyAttributionReport])
def get_all_strategy_attributions(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    attr_service: StrategyAttributionService = Depends(get_attribution_service),
) -> list[StrategyAttributionReport]:
    """Get attribution reports for all strategies in a portfolio."""
    return attr_service.get_all_strategy_attributions(db, portfolio_id)


@router.get("/attribution/{portfolio_id}/{strategy_id}", response_model=StrategyAttributionReport)
def get_strategy_attribution(
    portfolio_id: uuid.UUID,
    strategy_id: str,
    db: Session = Depends(get_db),
    attr_service: StrategyAttributionService = Depends(get_attribution_service),
) -> StrategyAttributionReport:
    """Get performance attribution report for a specific strategy."""
    return attr_service.get_strategy_attribution(db, portfolio_id, strategy_id)


@router.get("/leaderboard/{portfolio_id}", response_model=list[StrategyLeaderboardEntry])
def get_strategy_leaderboard(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    attr_service: StrategyAttributionService = Depends(get_attribution_service),
) -> list[StrategyLeaderboardEntry]:
    """Get strategy leaderboard ranked by net return."""
    return attr_service.get_strategy_leaderboard(db, portfolio_id)


# ── Market Regime ──────────────────────────────────────────────────────────────


@router.get("/regime/{portfolio_id}", response_model=RegimeStatisticsResponse)
def get_regime_statistics(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    regime_service: MarketRegimeAnalyzer = Depends(get_regime_analyzer),
) -> RegimeStatisticsResponse:
    """Get aggregate market regime statistics and strategy-regime matrix."""
    return regime_service.get_regime_statistics(db, portfolio_id)


# ── Portfolio Risk Analytics ───────────────────────────────────────────────────


@router.get("/risk/{portfolio_id}", response_model=PortfolioRiskAnalytics)
def get_portfolio_risk_analytics(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    risk_service: PortfolioRiskAnalyticsService = Depends(get_risk_analytics_service),
) -> PortfolioRiskAnalytics:
    """Get portfolio risk analytics: sector/symbol/strategy exposure, concentration HHI, cash utilization."""
    return risk_service.get_portfolio_risk_analytics(db, portfolio_id)


# ── Cost Profiles ──────────────────────────────────────────────────────────────


@router.get("/cost-profiles", response_model=list[CostProfileResponse])
def list_cost_profiles(
    db: Session = Depends(get_db),
    cost_service: CostProfileManager = Depends(get_cost_profile_manager),
) -> list[CostProfileResponse]:
    """List all persisted trading cost profiles."""
    records = cost_service.list_profiles(db)
    return [CostProfileResponse.model_validate(r) for r in records]


@router.post("/cost-profiles", response_model=CostProfileResponse)
def create_cost_profile(
    request: CostProfileCreateRequest,
    db: Session = Depends(get_db),
    cost_service: CostProfileManager = Depends(get_cost_profile_manager),
) -> CostProfileResponse:
    """Create and persist a custom trading cost profile."""
    record = cost_service.create_profile(db, request)
    return CostProfileResponse.model_validate(record)


@router.post("/cost-comparison", response_model=CostComparisonResponse)
def compare_cost_profiles(
    quantity: Decimal = Query(Decimal("100.0")),
    price: Decimal = Query(Decimal("1500.0")),
    profile_names: list[str] = Query(default=["zerodha_2026_v1", "groww_2026_v1", "icici_2026_v1"]),
    cost_service: CostProfileManager = Depends(get_cost_profile_manager),
) -> CostComparisonResponse:
    """Compare trade execution charges across multiple broker cost profiles."""
    return cost_service.get_cost_comparison(quantity, price, profile_names)


# ── Report Generator ───────────────────────────────────────────────────────────


@router.get("/reports/daily/{portfolio_id}", response_model=PeriodReportResponse)
def get_daily_report(
    portfolio_id: uuid.UUID,
    report_date: date | None = None,
    db: Session = Depends(get_db),
    report_service: ReportGeneratorService = Depends(get_report_generator_service),
) -> PeriodReportResponse:
    """Generate daily performance report."""
    target_date = report_date or date.today()
    return report_service.generate_daily_report(db, portfolio_id, target_date)


@router.get("/reports/weekly/{portfolio_id}", response_model=PeriodReportResponse)
def get_weekly_report(
    portfolio_id: uuid.UUID,
    week_start: date | None = None,
    db: Session = Depends(get_db),
    report_service: ReportGeneratorService = Depends(get_report_generator_service),
) -> PeriodReportResponse:
    """Generate weekly performance report."""
    target_date = week_start or (date.today() - __import__("datetime").timedelta(days=date.today().weekday()))
    return report_service.generate_weekly_report(db, portfolio_id, target_date)


@router.get("/reports/monthly/{portfolio_id}", response_model=PeriodReportResponse)
def get_monthly_report(
    portfolio_id: uuid.UUID,
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
    report_service: ReportGeneratorService = Depends(get_report_generator_service),
) -> PeriodReportResponse:
    """Generate monthly performance report."""
    now = datetime.now()
    y = year or now.year
    m = month or now.month
    return report_service.generate_monthly_report(db, portfolio_id, y, m)


# ── Alerts ─────────────────────────────────────────────────────────────────────


@router.get("/alerts/{portfolio_id}", response_model=list[AlertResponse])
def get_active_alerts(
    portfolio_id: uuid.UUID,
    evaluate: bool = True,
    db: Session = Depends(get_db),
    alert_engine: AlertEngine = Depends(get_alert_engine),
) -> list[AlertResponse]:
    """Get active unacknowledged alerts (runs evaluation if requested)."""
    if evaluate:
        alert_engine.evaluate_alerts(db, portfolio_id)
    alerts = alert_engine.get_active_alerts(db, portfolio_id)
    return [AlertResponse.model_validate(a) for a in alerts]


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: uuid.UUID,
    request: AlertAcknowledgeRequest = AlertAcknowledgeRequest(),
    db: Session = Depends(get_db),
    alert_engine: AlertEngine = Depends(get_alert_engine),
) -> dict[str, str]:
    """Acknowledge an operational alert."""
    success = alert_engine.acknowledge_alert(db, alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": f"Alert {alert_id} acknowledged"}


# ── Benchmark Comparison ───────────────────────────────────────────────────────


@router.post("/benchmark/{portfolio_id}", response_model=BenchmarkComparisonResponse)
def compare_benchmark(
    portfolio_id: uuid.UUID,
    request: BenchmarkComparisonRequest,
    db: Session = Depends(get_db),
    bench_service: BenchmarkComparisonService = Depends(get_benchmark_service),
) -> BenchmarkComparisonResponse:
    """Compare portfolio return series against a benchmark index."""
    return bench_service.compare_against_benchmark(
        db, portfolio_id, request.benchmark_series, request.benchmark_name
    )


# ── Monte Carlo & Walk-Forward ─────────────────────────────────────────────────


@router.post("/monte-carlo/{portfolio_id}", response_model=MonteCarloAnalysisResponse)
def run_monte_carlo(
    portfolio_id: uuid.UUID,
    request: MonteCarloRequest = MonteCarloRequest(),
    db: Session = Depends(get_db),
    val_service: ValidationService = Depends(get_validation_service),
) -> MonteCarloAnalysisResponse:
    """Run Monte Carlo trade sequence resampling on paper trading PnLs."""
    return val_service.run_monte_carlo(db, portfolio_id, request)


@router.post("/walk-forward/{portfolio_id}", response_model=WalkForwardAnalysisResponse)
def run_walk_forward(
    portfolio_id: uuid.UUID,
    request: WalkForwardRequest = WalkForwardRequest(),
    db: Session = Depends(get_db),
    val_service: ValidationService = Depends(get_validation_service),
) -> WalkForwardAnalysisResponse:
    """Run Walk-Forward validation partitioning on paper trading timeline."""
    return val_service.run_walk_forward(db, portfolio_id, request)


# ── Strategy Version Tracking ──────────────────────────────────────────────────


@router.get("/strategy-versions/{strategy_id}", response_model=StrategyVersionComparisonResponse)
def get_strategy_version_history(
    strategy_id: str,
    portfolio_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    vt_service: StrategyVersionTracker = Depends(get_version_tracker),
) -> StrategyVersionComparisonResponse:
    """Compare strategy version performance over time."""
    return vt_service.get_version_history(db, strategy_id, portfolio_id)


# ── Dashboard Aggregate ────────────────────────────────────────────────────────


@router.get("/dashboard/{portfolio_id}", response_model=PaperTradingDashboardResponse)
def get_paper_trading_dashboard(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    perf_service: PerformanceAnalyticsService = Depends(get_performance_analytics_service),
    journal_service: TradeJournalService = Depends(get_trade_journal_service),
    risk_service: PortfolioRiskAnalyticsService = Depends(get_risk_analytics_service),
    alert_engine: AlertEngine = Depends(get_alert_engine),
) -> PaperTradingDashboardResponse:
    """Aggregate high-level paper trading validation dashboard."""
    report = perf_service.calculate_gross_net_report(db, portfolio_id)
    trades = journal_service.get_all_portfolio_trades(db, portfolio_id)
    risk = risk_service.get_portfolio_risk_analytics(db, portfolio_id)
    active_alerts = alert_engine.get_active_alerts(db, portfolio_id)
    strategies = journal_service.get_distinct_strategies(db, portfolio_id)

    positions_count = len(db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.status == "open",
        )
    ).scalars().all())

    return PaperTradingDashboardResponse(
        portfolio_id=portfolio_id,
        generated_at=datetime.now(),
        open_positions_count=positions_count,
        closed_trades_count=len(trades),
        gross_performance=report.gross,
        net_performance=report.net,
        total_costs_incurred=report.total_costs_incurred,
        active_alerts_count=len(active_alerts),
        strategy_count=len(strategies),
        cash_utilization_pct=risk.cash_utilization_pct,
    )
