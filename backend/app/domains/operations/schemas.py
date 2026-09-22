"""API Schemas for Phase 10 Operations endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.domains.operations.models import (
    ExperimentConfig,
    OperationalMode,
    PortfolioDailySnapshot,
)


# --- Autonomous Scheduler Schemas ---
class SchedulerConfigSchema(BaseModel):
    interval_seconds: float = 60.0
    auto_start_pre_market: bool = True
    auto_stop_post_market: bool = True
    respect_holidays: bool = True
    respect_weekends: bool = True
    mode: OperationalMode = OperationalMode.autonomous


class SchedulerStatusResponse(BaseModel):
    mode: OperationalMode
    is_running: bool
    is_market_open: bool
    is_weekend: bool
    is_holiday: bool
    interval_seconds: float
    last_run_timestamp: str | None = None
    next_run_timestamp: str | None = None
    total_execution_cycles: int = 0
    recent_execution_history: list[dict[str, Any]] = Field(default_factory=list)


class SchedulerControlRequest(BaseModel):
    action: str  # start, stop, pause, resume, manual_override
    manual_mode_override: bool = False


# --- Daily Snapshot Schemas ---
class SnapshotQueryRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    limit: int = 30


class SnapshotListResponse(BaseModel):
    total_snapshots: int
    snapshots: list[PortfolioDailySnapshot]


# --- Report Generation Schemas ---
class ReportGenerationRequest(BaseModel):
    report_type: str  # daily, weekly, monthly
    start_date: str
    end_date: str
    export_format: str = "json"  # pdf, html, csv, json


class OperationalReportResponse(BaseModel):
    report_id: str
    report_type: str
    period_start: str
    period_end: str
    format: str
    portfolio_summary: dict[str, Any]
    gross_performance: dict[str, Any]
    net_performance: dict[str, Any]
    trade_summary: dict[str, Any]
    win_loss_analysis: dict[str, Any]
    strategy_rankings: list[dict[str, Any]]
    risk_analysis: dict[str, Any]
    exposure: dict[str, Any]
    cost_analysis: dict[str, Any]
    drawdown_analysis: dict[str, Any]
    benchmark_comparison: dict[str, Any]
    regime_performance: dict[str, Any]
    alerts_triggered: list[dict[str, Any]]
    rendered_content: str | None = None  # Base64 or formatted string for PDF/HTML/CSV
    generated_at: str


# --- Replay Dashboard Schemas ---
class DashboardReplayResponse(BaseModel):
    equity_curve: list[dict[str, Any]]
    capital_deployment: list[dict[str, Any]]
    trade_sequence: list[dict[str, Any]]
    position_history: list[dict[str, Any]]
    cash_movement: list[dict[str, Any]]
    risk_evolution: list[dict[str, Any]]
    cost_accumulation: list[dict[str, Any]]
    gross_vs_net_equity: list[dict[str, Any]]


# --- Replay Action Schema ---
class ReplayActionRequest(BaseModel):
    action: str  # play, pause, step_forward, step_backward, seek
    target_step: int | None = None
    speed_multiplier: float = 1.0


# --- Research Experiment Request ---
class CreateExperimentRequest(BaseModel):
    name: str
    description: str = ""
    experiment_type: str  # A/B_testing, parameter_comparison, indicator_comparison
    config: ExperimentConfig


# --- Historical Comparison Request ---
class HistoricalComparisonRequest(BaseModel):
    comparison_type: str  # day_v_day, week_v_week, month_v_month, version_v_version, cost_v_cost
    baseline_id_or_period: str
    target_id_or_period: str


# --- Research Note Request ---
class CreateResearchNoteRequest(BaseModel):
    entity_type: str
    entity_id: str
    author: str
    title: str
    content_markdown: str
    tags: list[str] = Field(default_factory=list)


# --- Data Export & Import Request ---
class DataExportRequest(BaseModel):
    data_type: str  # trade_journal, portfolio_snapshots, analytics, reports, experiments, alerts
    export_format: str  # csv, excel, json, pdf
    start_date: str | None = None
    end_date: str | None = None


class DataImportResponse(BaseModel):
    records_imported: int
    data_type: str
    status: str
    details: str
