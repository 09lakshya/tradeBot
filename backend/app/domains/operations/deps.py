"""Dependency Injection providers for Operations domain."""
from __future__ import annotations

from app.domains.operations.alert_center import OperationalAlertCenter
from app.domains.operations.autonomous_scheduler import AutonomousScheduler
from app.domains.operations.dashboard_service import DashboardService
from app.domains.operations.data_exporter import DataExporterEngine
from app.domains.operations.decision_replay import DecisionReplayEngine
from app.domains.operations.explainability_engine import StrategyExplainabilityEngine
from app.domains.operations.historical_comparison import HistoricalComparisonEngine
from app.domains.operations.readiness_assessment import ReadinessAssessmentEngine
from app.domains.operations.report_generator import AutomatedReportGenerator
from app.domains.operations.research_notes import ResearchNotesEngine
from app.domains.operations.research_workspace import ResearchWorkspaceEngine
from app.domains.operations.snapshot_engine import DailySnapshotEngine
from app.domains.operations.strategy_health import StrategyHealthMonitor

# Global singleton instances for thread-safe in-memory operations
_scheduler = AutonomousScheduler()
_snapshot_engine = DailySnapshotEngine()
_explainability_engine = StrategyExplainabilityEngine()
_replay_engine = DecisionReplayEngine()
_health_monitor = StrategyHealthMonitor()
_research_workspace = ResearchWorkspaceEngine()
_historical_comparison = HistoricalComparisonEngine()
_dashboard_service = DashboardService()
_alert_center = OperationalAlertCenter()
_readiness_engine = ReadinessAssessmentEngine()
_report_generator = AutomatedReportGenerator()
_notes_engine = ResearchNotesEngine()
_exporter = DataExporterEngine()


def get_scheduler() -> AutonomousScheduler:
    return _scheduler


def get_snapshot_engine() -> DailySnapshotEngine:
    return _snapshot_engine


def get_explainability_engine() -> StrategyExplainabilityEngine:
    return _explainability_engine


def get_replay_engine() -> DecisionReplayEngine:
    return _replay_engine


def get_health_monitor() -> StrategyHealthMonitor:
    return _health_monitor


def get_research_workspace() -> ResearchWorkspaceEngine:
    return _research_workspace


def get_historical_comparison() -> HistoricalComparisonEngine:
    return _historical_comparison


def get_dashboard_service() -> DashboardService:
    return _dashboard_service


def get_alert_center() -> OperationalAlertCenter:
    return _alert_center


def get_readiness_engine() -> ReadinessAssessmentEngine:
    return _readiness_engine


def get_report_generator() -> AutomatedReportGenerator:
    return _report_generator


def get_notes_engine() -> ResearchNotesEngine:
    return _notes_engine


def get_exporter() -> DataExporterEngine:
    return _exporter
