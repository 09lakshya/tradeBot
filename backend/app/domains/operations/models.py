"""Domain models for Phase 10 Autonomous Operations, Explainability & Research Workspace."""
from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class OperationalMode(str, enum.Enum):
    autonomous = "autonomous"
    manual_override = "manual_override"
    paused = "paused"
    stopped = "stopped"


class AlertSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class ReadinessStatus(str, enum.Enum):
    ready_for_live_pilot = "READY FOR LIVE PILOT"
    needs_continuous_paper_trading = "NEEDS CONTINUOUS PAPER TRADING"
    not_ready = "NOT READY FOR LIVE DEPLOYMENT"


class ExperimentStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


# --- 1. Portfolio Daily Snapshot ---
class PortfolioDailySnapshot(BaseModel):
    """Immutable daily portfolio snapshot."""

    snapshot_id: str = Field(default_factory=lambda: str(uuid4()))
    date: str
    portfolio_value: float
    cash_balance: float
    invested_capital: float
    unrealized_pnl: float
    realized_pnl: float
    gross_return: float
    net_return: float
    drawdown: float
    open_positions_count: int
    closed_trades_count: int
    open_positions: list[dict[str, Any]] = Field(default_factory=list)
    closed_trades: list[dict[str, Any]] = Field(default_factory=list)
    risk_metrics: dict[str, float] = Field(default_factory=dict)
    strategy_allocation: dict[str, float] = Field(default_factory=dict)
    exposure: dict[str, float] = Field(default_factory=dict)
    cost_breakdown: dict[str, float] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# --- 2. Strategy Explainability ---
class SignalReason(BaseModel):
    indicators_involved: list[str]
    indicator_values: dict[str, float]
    confidence_score: float
    rationale: str


class RiskReason(BaseModel):
    approved: bool
    rules_evaluated: list[str]
    violated_rules: list[str] = Field(default_factory=list)
    rationale: str


class PortfolioReason(BaseModel):
    accepted: bool
    position_sizing_selected: float
    sizing_rationale: str
    allocation_weight: float


class ExecutionReason(BaseModel):
    executed: bool
    fill_price: float
    slippage: float
    commission: float
    rationale: str


class TradeExplanation(BaseModel):
    """Full causal decision lineage explaining why a trade was executed or exited."""

    explanation_id: str = Field(default_factory=lambda: str(uuid4()))
    trade_id: str
    order_id: str | None = None
    strategy_id: str
    symbol: str
    side: str  # BUY or SELL
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    signal_reason: SignalReason
    risk_reason: RiskReason
    portfolio_reason: PortfolioReason
    execution_reason: ExecutionReason
    exit_reason: str | None = None
    narrative: str


# --- 3. Strategy Health Monitoring ---
class StrategyHealthReport(BaseModel):
    """Health metrics and degradation monitoring for a single strategy."""

    strategy_id: str
    win_rate: float
    baseline_win_rate: float
    win_rate_drift: float
    profit_factor: float
    baseline_profit_factor: float
    profit_factor_drift: float
    sharpe_ratio: float
    baseline_sharpe: float
    sharpe_drift: float
    current_drawdown: float
    max_drawdown_increase: float
    signal_frequency_per_day: float
    trade_frequency_per_day: float
    regime_performance: dict[str, float] = Field(default_factory=dict)
    recent_pnl_30d: float
    is_degraded: bool
    degradation_reasons: list[str] = Field(default_factory=list)
    evaluated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# --- 4. Research & Experiment Workspace ---
class ExperimentConfig(BaseModel):
    strategy_id: str
    symbols: list[str]
    start_date: str
    end_date: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    cost_profile: str = "institutional_standard"


class ExperimentResult(BaseModel):
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    net_pnl: float
    metrics: dict[str, float] = Field(default_factory=dict)


class ResearchExperiment(BaseModel):
    """Isolated research experiment metadata and results."""

    experiment_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str = ""
    experiment_type: str  # A/B_testing, parameter_comparison, indicator_comparison
    status: ExperimentStatus = ExperimentStatus.pending
    config: ExperimentConfig
    baseline_results: ExperimentResult | None = None
    variant_results: dict[str, ExperimentResult] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None


# --- 5. Historical Comparison Engine ---
class PerformanceDiff(BaseModel):
    baseline_val: float
    target_val: float
    absolute_diff: float
    percentage_change: float


class HistoricalComparisonResult(BaseModel):
    comparison_type: str  # day_v_day, week_v_week, month_v_month, version_v_version, cost_v_cost
    baseline_label: str
    target_label: str
    metrics_comparison: dict[str, PerformanceDiff]
    summary_insight: str
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# --- 6. Readiness Assessment Engine ---
class PillarScore(BaseModel):
    name: str
    score: float  # 0 to 100
    weight: float  # e.g., 0.10
    weighted_score: float
    details: str


class ReadinessAssessment(BaseModel):
    """Institutional readiness score for live deployment eligibility."""

    assessment_id: str = Field(default_factory=lambda: str(uuid4()))
    overall_score: float  # 0 to 100
    status: ReadinessStatus
    pillars: list[PillarScore]
    passed_criteria_count: int
    total_criteria_count: int
    recommendations: list[str]
    evaluated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# --- 7. Research Notes & Annotation ---
class ResearchNote(BaseModel):
    note_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_type: str  # strategy, experiment, trading_day, snapshot, report, version
    entity_id: str
    author: str
    title: str
    content_markdown: str
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# --- 8. Operational Alerts ---
class OperationalAlert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    severity: AlertSeverity
    alert_type: str  # strategy_degradation, high_slippage, high_costs, drawdown_threshold, etc.
    title: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    resolved: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None


# --- 9. Replay Session ---
class ReplayStep(BaseModel):
    step_number: int
    timestamp: str
    market_prices: dict[str, float]
    signals_generated: list[dict[str, Any]]
    portfolio_decisions: list[dict[str, Any]]
    risk_evaluations: list[dict[str, Any]]
    orders_issued: list[dict[str, Any]]
    positions_state: list[dict[str, Any]]
    portfolio_value: float
    cash_balance: float


class ReplaySessionState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    date: str
    current_step: int = 0
    total_steps: int = 0
    is_playing: bool = False
    speed_multiplier: float = 1.0
    steps: list[ReplayStep] = Field(default_factory=list)
