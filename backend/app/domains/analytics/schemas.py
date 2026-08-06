"""Pydantic v2 schemas and DTOs for the Analytics domain REST API."""
from __future__ import annotations

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domains.analytics.enums import (
    AlertSeverity,
    AlertType,
    BenchmarkIndex,
    ExitReason,
    MarketRegimeClassification,
    ReportPeriod,
)


# ── Trade Journal ──────────────────────────────────────────────────────────────


class DetailedCostBreakdown(BaseModel):
    """Full itemized cost decomposition for a single trade."""
    brokerage: Decimal = Decimal("0.0000")
    stt: Decimal = Decimal("0.0000")
    exchange_charges: Decimal = Decimal("0.0000")
    gst: Decimal = Decimal("0.0000")
    stamp_duty: Decimal = Decimal("0.0000")
    sebi_charges: Decimal = Decimal("0.0000")
    slippage: Decimal = Decimal("0.0000")
    market_impact: Decimal = Decimal("0.0000")
    dp_charges: Decimal = Decimal("0.0000")
    broker_total: Decimal = Decimal("0.0000")
    government_total: Decimal = Decimal("0.0000")
    execution_total: Decimal = Decimal("0.0000")
    total_charges: Decimal = Decimal("0.0000")


class TradeJournalEntryResponse(BaseModel):
    """Complete trade journal entry response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    trade_id: str
    strategy_id: str
    strategy_version: str
    parameter_snapshot_id: uuid.UUID | None
    symbol: str
    sector: str | None
    entry_timestamp: datetime
    exit_timestamp: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    position_size_pct: Decimal
    holding_duration_seconds: int
    stop_loss: Decimal | None
    take_profit: Decimal | None
    exit_reason: ExitReason
    signal_confidence: Decimal
    risk_reward_ratio: Decimal | None
    gross_pnl: Decimal
    net_pnl: Decimal
    gross_return_pct: Decimal
    net_return_pct: Decimal
    mfe: Decimal
    mae: Decimal
    cost_breakdown: dict[str, Any]
    cost_profile_version: str
    market_regime: str
    portfolio_snapshot_id: uuid.UUID | None
    entry_order_id: uuid.UUID | None
    exit_order_id: uuid.UUID | None
    config_snapshot: dict[str, Any]
    created_at: datetime


class TradeJournalFilterRequest(BaseModel):
    """Filtering parameters for trade journal queries."""
    portfolio_id: uuid.UUID
    start_date: datetime | None = None
    end_date: datetime | None = None
    strategy_id: str | None = None
    symbol: str | None = None
    exit_reason: ExitReason | None = None
    min_return_pct: Decimal | None = None
    max_return_pct: Decimal | None = None
    market_regime: str | None = None
    limit: int = Field(default=100, ge=1, le=10000)

    offset: int = Field(default=0, ge=0)


class TradeJournalExportResponse(BaseModel):
    """Export wrapper for trade journal data."""
    portfolio_id: uuid.UUID
    total_trades: int
    export_timestamp: datetime
    trades: list[TradeJournalEntryResponse]


# ── Cost Profiles ──────────────────────────────────────────────────────────────


class CostProfileCreateRequest(BaseModel):
    """Request to create a custom cost profile."""
    profile_name: str = Field(..., max_length=100)
    version: str = Field(default="1.0.0", max_length=30)
    description: str = Field(default="", max_length=500)
    brokerage_flat: Decimal = Decimal("20.0000")
    brokerage_pct: Decimal = Decimal("0.0003")
    brokerage_cap: Decimal = Decimal("20.0000")
    brokerage_delivery_zero: bool = True
    stt_delivery_buy_pct: Decimal = Decimal("0.0010")
    stt_delivery_sell_pct: Decimal = Decimal("0.0010")
    stt_intraday_buy_pct: Decimal = Decimal("0.0000")
    stt_intraday_sell_pct: Decimal = Decimal("0.00025")
    exchange_txn_nse_pct: Decimal = Decimal("0.0000297")
    exchange_txn_bse_pct: Decimal = Decimal("0.0000375")
    sebi_turnover_pct: Decimal = Decimal("0.0000010")
    stamp_duty_delivery_buy_pct: Decimal = Decimal("0.00015")
    stamp_duty_delivery_sell_pct: Decimal = Decimal("0.0000")
    stamp_duty_intraday_buy_pct: Decimal = Decimal("0.00003")
    stamp_duty_intraday_sell_pct: Decimal = Decimal("0.0000")
    gst_pct: Decimal = Decimal("0.1800")
    dp_charges: Decimal = Decimal("0.0000")
    slippage_bps: Decimal = Decimal("5.0")
    market_impact_bps: Decimal = Decimal("0.0")


class CostProfileResponse(BaseModel):
    """Cost profile summary response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_name: str
    version: str
    is_active: bool
    description: str
    profile_data: dict[str, Any]
    created_at: datetime


class CostComparisonResponse(BaseModel):
    """Side-by-side cost comparison across multiple profiles."""
    quantity: Decimal
    price: Decimal
    turnover: Decimal
    profiles: dict[str, DetailedCostBreakdown]


# ── Performance Analytics ──────────────────────────────────────────────────────


class PerformanceMetrics(BaseModel):
    """Comprehensive performance metrics (gross or net)."""
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    daily_return_pct: float = 0.0
    monthly_return_pct: float = 0.0
    annual_return_pct: float = 0.0
    annualized_volatility_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float | None = None
    alpha: float | None = None
    beta: float | None = None
    win_rate_pct: float = 0.0
    loss_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    recovery_time_days: int | None = None
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    omega_ratio: float = 0.0
    payoff_ratio: float = 0.0


class GrossNetPerformanceReport(BaseModel):
    """Side-by-side gross and net performance."""
    portfolio_id: uuid.UUID
    calculation_timestamp: datetime
    initial_capital: Decimal
    current_equity_gross: Decimal
    current_equity_net: Decimal
    total_costs_incurred: Decimal
    gross: PerformanceMetrics
    net: PerformanceMetrics


class ReturnEntry(BaseModel):
    """Single return period entry."""
    period: str  # date string or label
    gross_return_pct: float = 0.0
    net_return_pct: float = 0.0
    gross_pnl: Decimal = Decimal("0.0000")
    net_pnl: Decimal = Decimal("0.0000")


# ── Equity Curve ───────────────────────────────────────────────────────────────


class EquityCurvePoint(BaseModel):
    """Single point on an equity curve."""
    timestamp: datetime
    gross_equity: Decimal
    net_equity: Decimal
    cash_balance: Decimal
    invested_value: Decimal


class EquityCurveResponse(BaseModel):
    """Equity curve time-series."""
    portfolio_id: uuid.UUID
    points: list[EquityCurvePoint]
    initial_capital: Decimal
    gross_total_return_pct: float
    net_total_return_pct: float


class DrawdownCurvePoint(BaseModel):
    """Single point on a drawdown curve."""
    timestamp: datetime
    gross_drawdown_pct: Decimal
    net_drawdown_pct: Decimal


class DrawdownCurveResponse(BaseModel):
    """Drawdown curve time-series."""
    portfolio_id: uuid.UUID
    points: list[DrawdownCurvePoint]
    max_gross_drawdown_pct: float
    max_net_drawdown_pct: float


# ── Strategy Attribution ───────────────────────────────────────────────────────


class StrategyAttributionReport(BaseModel):
    """Comprehensive performance attribution for a single strategy."""
    strategy_id: str
    strategy_version: str
    signals_generated: int = 0
    signals_accepted: int = 0
    signals_rejected: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_pct: float = 0.0
    gross_return_pct: float = 0.0
    net_return_pct: float = 0.0
    gross_pnl: Decimal = Decimal("0.0000")
    net_pnl: Decimal = Decimal("0.0000")
    average_holding_seconds: int = 0
    best_symbols: list[dict[str, Any]] = Field(default_factory=list)
    worst_symbols: list[dict[str, Any]] = Field(default_factory=list)
    regime_performance: dict[str, dict[str, float]] = Field(default_factory=dict)
    portfolio_contribution_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0


class StrategyLeaderboardEntry(BaseModel):
    """Entry in the strategy leaderboard ranking."""
    rank: int
    strategy_id: str
    total_trades: int
    win_rate_pct: float
    net_return_pct: float
    net_pnl: Decimal
    sharpe_ratio: float
    profit_factor: float
    portfolio_contribution_pct: float


# ── Market Regime ──────────────────────────────────────────────────────────────


class RegimePerformanceEntry(BaseModel):
    """Performance under a specific market regime."""
    regime: str
    trade_count: int = 0
    win_rate_pct: float = 0.0
    avg_return_pct: float = 0.0
    total_pnl: Decimal = Decimal("0.0000")
    sharpe_ratio: float = 0.0


class RegimeStatisticsResponse(BaseModel):
    """Aggregate regime performance statistics."""
    portfolio_id: uuid.UUID
    regime_stats: list[RegimePerformanceEntry]
    strategy_regime_matrix: dict[str, list[RegimePerformanceEntry]] = Field(default_factory=dict)
    regime_distribution: dict[str, float] = Field(default_factory=dict)


# ── Portfolio Risk Analytics ───────────────────────────────────────────────────


class ExposureEntry(BaseModel):
    """Exposure for a single category (sector, symbol, strategy)."""
    name: str
    market_value: Decimal = Decimal("0.0000")
    weight_pct: float = 0.0
    pnl: Decimal = Decimal("0.0000")


class PortfolioRiskAnalytics(BaseModel):
    """Comprehensive portfolio risk analytics snapshot."""
    portfolio_id: uuid.UUID
    timestamp: datetime
    sector_exposure: list[ExposureEntry] = Field(default_factory=list)
    symbol_exposure: list[ExposureEntry] = Field(default_factory=list)
    strategy_exposure: list[ExposureEntry] = Field(default_factory=list)
    cash_utilization_pct: float = 0.0
    capital_utilization_pct: float = 0.0
    concentration_hhi: float = 0.0
    top_5_concentration_pct: float = 0.0
    correlation_matrix: dict[str, dict[str, float]] = Field(default_factory=dict)
    position_count: int = 0
    position_size_distribution: dict[str, int] = Field(default_factory=dict)


# ── Reports ────────────────────────────────────────────────────────────────────


class TradeSummary(BaseModel):
    """Summary of trading activity for a report period."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    best_trade_pnl: Decimal = Decimal("0.0000")
    best_trade_symbol: str = ""
    worst_trade_pnl: Decimal = Decimal("0.0000")
    worst_trade_symbol: str = ""


class PeriodReportResponse(BaseModel):
    """Generalized report for daily/weekly/monthly periods."""
    portfolio_id: uuid.UUID
    period: str
    period_type: ReportPeriod
    generated_at: datetime
    portfolio_summary: dict[str, Any] = Field(default_factory=dict)
    gross_return_pct: float = 0.0
    net_return_pct: float = 0.0
    gross_pnl: Decimal = Decimal("0.0000")
    net_pnl: Decimal = Decimal("0.0000")
    trade_summary: TradeSummary = Field(default_factory=TradeSummary)
    risk_metrics: dict[str, float] = Field(default_factory=dict)
    best_strategy: str | None = None
    worst_strategy: str | None = None
    largest_drawdown_pct: float = 0.0
    cost_analysis: DetailedCostBreakdown = Field(default_factory=DetailedCostBreakdown)
    exposure: dict[str, Any] = Field(default_factory=dict)
    strategy_rankings: list[StrategyLeaderboardEntry] = Field(default_factory=list)


# ── Alerts ─────────────────────────────────────────────────────────────────────


class AlertResponse(BaseModel):
    """Analytics alert response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    metric_name: str
    metric_value: Decimal
    threshold_value: Decimal
    strategy_id: str | None
    is_acknowledged: bool
    created_at: datetime


class AlertAcknowledgeRequest(BaseModel):
    """Request to acknowledge an alert."""
    acknowledged_by: str = "system"


# ── Benchmark ──────────────────────────────────────────────────────────────────


class BenchmarkComparisonRequest(BaseModel):
    """Request for benchmark comparison."""
    benchmark_name: str = "nifty_50"
    benchmark_series: list[float] = Field(default_factory=list)


class BenchmarkComparisonResponse(BaseModel):
    """Benchmark comparison result."""
    portfolio_id: uuid.UUID
    benchmark_name: str
    portfolio_return_pct: float = 0.0
    benchmark_return_pct: float = 0.0
    excess_return_pct: float = 0.0
    tracking_error: float = 0.0
    information_ratio: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    relative_max_drawdown_pct: float = 0.0


# ── Monte Carlo & Walk-Forward ─────────────────────────────────────────────────


class MonteCarloRequest(BaseModel):
    """Request for Monte Carlo simulation."""
    iterations: int = Field(default=10000, ge=100, le=100000)
    random_seed: int = 42
    ruin_threshold_pct: float = 50.0
    block_size: int = 5
    sample_paths: int = Field(default=10, ge=1, le=50)


class MonteCarloAnalysisResponse(BaseModel):
    """Monte Carlo analysis result."""
    portfolio_id: uuid.UUID
    iterations: int
    probability_of_ruin: float
    expected_drawdown_pct: float
    confidence_intervals: dict[str, float]
    return_distribution: dict[str, float]
    expected_portfolio_growth_pct: float
    var_95: float
    cvar_95: float
    sample_equity_paths: list[list[float]] = Field(default_factory=list)


class WalkForwardRequest(BaseModel):
    """Request for walk-forward validation."""
    training_window_days: int = Field(default=90, ge=30)
    testing_window_days: int = Field(default=30, ge=10)
    purge_days: int = Field(default=5, ge=0)
    embargo_days: int = Field(default=2, ge=0)



class WalkForwardAnalysisResponse(BaseModel):
    """Walk-forward validation result."""
    portfolio_id: uuid.UUID
    total_windows: int
    mean_is_sharpe: float
    mean_oos_sharpe: float
    mean_wfe_ratio: float
    window_results: list[dict[str, Any]] = Field(default_factory=list)


# ── Strategy Version Tracking ──────────────────────────────────────────────────


class StrategyVersionEntry(BaseModel):
    """A single version snapshot for a strategy."""
    strategy_id: str
    strategy_version: str
    parameter_snapshot_id: uuid.UUID | None
    config_snapshot: dict[str, Any]
    trade_count: int
    win_rate_pct: float
    net_return_pct: float
    net_pnl: Decimal
    first_trade: datetime | None
    last_trade: datetime | None


class StrategyVersionComparisonResponse(BaseModel):
    """Comparison between strategy versions."""
    strategy_id: str
    versions: list[StrategyVersionEntry]


# ── Dashboard ──────────────────────────────────────────────────────────────────


class PaperTradingDashboardResponse(BaseModel):
    """Aggregate paper trading dashboard."""
    portfolio_id: uuid.UUID
    generated_at: datetime
    open_positions_count: int = 0
    closed_trades_count: int = 0
    gross_performance: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    net_performance: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    total_costs_incurred: Decimal = Decimal("0.0000")
    active_alerts_count: int = 0
    strategy_count: int = 0
    best_strategy: str | None = None
    worst_strategy: str | None = None
    current_drawdown_pct: float = 0.0
    cash_utilization_pct: float = 0.0
