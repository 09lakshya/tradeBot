"""Dependency injection helpers for the Analytics domain."""
from typing import Generator
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.analytics.alerts import AlertEngine
from app.domains.analytics.attribution import StrategyAttributionService
from app.domains.analytics.benchmark import BenchmarkComparisonService
from app.domains.analytics.cost_profiles import CostProfileManager
from app.domains.analytics.equity_curve import EquityCurveService
from app.domains.analytics.performance import PerformanceAnalyticsService
from app.domains.analytics.regime import MarketRegimeAnalyzer
from app.domains.analytics.reports import ReportGeneratorService
from app.domains.analytics.risk_analytics import PortfolioRiskAnalyticsService
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.analytics.validation import ValidationService
from app.domains.analytics.version_tracker import StrategyVersionTracker


def get_trade_journal_service() -> TradeJournalService:
    return TradeJournalService()


def get_cost_profile_manager() -> CostProfileManager:
    return CostProfileManager()


def get_performance_analytics_service() -> PerformanceAnalyticsService:
    return PerformanceAnalyticsService()


def get_equity_curve_service() -> EquityCurveService:
    return EquityCurveService()


def get_attribution_service() -> StrategyAttributionService:
    return StrategyAttributionService()


def get_regime_analyzer() -> MarketRegimeAnalyzer:
    return MarketRegimeAnalyzer()


def get_risk_analytics_service() -> PortfolioRiskAnalyticsService:
    return PortfolioRiskAnalyticsService()


def get_report_generator_service() -> ReportGeneratorService:
    return ReportGeneratorService()


def get_alert_engine() -> AlertEngine:
    return AlertEngine()


def get_benchmark_service() -> BenchmarkComparisonService:
    return BenchmarkComparisonService()


def get_version_tracker() -> StrategyVersionTracker:
    return StrategyVersionTracker()


def get_validation_service() -> ValidationService:
    return ValidationService()
