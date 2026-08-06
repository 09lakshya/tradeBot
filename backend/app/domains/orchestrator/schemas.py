"""Pydantic schemas and DTOs for the Execution Orchestrator domain."""
from datetime import datetime
from decimal import Decimal
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domains.orchestrator.enums import CycleStatus, OrchestratorMode, SessionState
from app.domains.portfolio.schemas import PortfolioConstructionConfig


class ExecutionCycleRequest(BaseModel):
    """Request payload to trigger an orchestrator execution cycle."""
    portfolio_id: uuid.UUID
    mode: OrchestratorMode = OrchestratorMode.paper
    strategy_ids: list[str] | None = None
    enforce_market_hours: bool = True
    config: PortfolioConstructionConfig | None = None


class ExecutionCycleResult(BaseModel):
    """Result summary of an orchestrator execution cycle."""
    cycle_id: uuid.UUID
    portfolio_id: uuid.UUID
    timestamp: datetime
    mode: OrchestratorMode
    duration_ms: float
    status: CycleStatus
    signals_evaluated_count: int
    candidate_orders_count: int
    risk_approved_count: int
    risk_rejected_count: int
    orders_submitted_count: int
    orders_filled_count: int
    stage_latencies: dict[str, float]
    error_message: str | None = None


class SessionStatusResponse(BaseModel):
    """Status details of Indian equity market trading session."""
    exchange: str = "NSE"
    session_state: SessionState
    is_market_open: bool
    is_holiday: bool
    is_half_day: bool
    current_time_ist: str
    next_transition_time: str | None = None
    holiday_name: str | None = None


class PipelineStatusResponse(BaseModel):
    """High-level operational health and status of the execution pipeline."""
    is_running: bool
    scheduler_active: bool
    current_mode: OrchestratorMode
    last_cycle_timestamp: datetime | None = None
    last_cycle_status: CycleStatus | None = None
    total_cycles_executed: int
    average_cycle_duration_ms: float


class SubsystemHealth(BaseModel):
    """Health diagnostic for an individual subsystem."""
    status: str  # healthy, degraded, unhealthy
    latency_ms: float
    last_check: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class HealthMetricsResponse(BaseModel):
    """Aggregate health status and latencies across all subsystems."""
    overall_status: str  # healthy, degraded, unhealthy
    timestamp: datetime
    subsystems: dict[str, SubsystemHealth]
    total_pipeline_latency_target_ms: float = 100.0


class ContinuousMetricsResponse(BaseModel):
    """Continuous financial and operational performance metrics."""
    portfolio_id: uuid.UUID
    timestamp: datetime
    total_equity: Decimal
    cash_balance: Decimal
    total_pnl: Decimal
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    turnover_ratio: float = 0.0
    cash_utilization_pct: float = 0.0
    total_trades: int = 0


class InvariantReportResponse(BaseModel):
    """Comprehensive invariant reconciliation and verification report."""
    timestamp: datetime
    all_passed: bool
    cash_reconciled: bool
    ledger_balanced: bool
    positions_consistent: bool
    risk_audit_consistent: bool
    discrepancy_details: dict[str, Any] | None = None
