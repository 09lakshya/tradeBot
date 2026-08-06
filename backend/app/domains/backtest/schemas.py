"""Pydantic schemas for the Backtest domain."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.domains.backtest.enums import (
    BacktestSegmentType,
    BacktestStatus,
    BenchmarkSymbol,
    SlippageModelType,
    ValidationMethod,
    WindowType,
)


class SlippageConfig(BaseModel):
    model_type: SlippageModelType = SlippageModelType.fixed_bps
    fixed_bps: Decimal = Field(default=Decimal("5.0000"), ge=Decimal("0.0"), le=Decimal("500.0"))
    spread_pct: Decimal = Field(default=Decimal("0.5000"), ge=Decimal("0.0"), le=Decimal("2.0"))
    volume_share_cap: Decimal = Field(default=Decimal("0.1000"), ge=Decimal("0.001"), le=Decimal("1.0"))
    impact_constant_k: Decimal = Field(default=Decimal("0.1000"), ge=Decimal("0.0"), le=Decimal("10.0"))


class WalkForwardConfig(BaseModel):
    window_type: WindowType = WindowType.rolling
    train_period_days: int = Field(default=252, ge=30, le=1260)
    test_period_days: int = Field(default=63, ge=10, le=252)
    step_days: int = Field(default=63, ge=10, le=252)
    purge_window_days: int = Field(default=5, ge=0, le=30)
    embargo_pct: Decimal = Field(default=Decimal("0.0100"), ge=Decimal("0.0"), le=Decimal("0.10"))


class MonteCarloConfig(BaseModel):
    iterations: int = Field(default=1000, ge=100, le=10000)
    resample_method: str = Field(default="block_bootstrap")
    block_size: int = Field(default=5, ge=1, le=50)
    confidence_level: Decimal = Field(default=Decimal("0.9500"), ge=Decimal("0.80"), le=Decimal("0.999"))
    ruin_drawdown_threshold: Decimal = Field(default=Decimal("0.2500"), ge=Decimal("0.05"), le=Decimal("0.90"))
    random_seed: int = Field(default=42)


class BacktestCreateRequest(BaseModel):
    name: str = Field(default="Backtest Run", max_length=120)
    strategy_id: str = Field(..., max_length=100)
    strategy_version: str = Field(default="1.0.0", max_length=50)
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    
    instrument_ids: list[uuid.UUID] = Field(..., min_length=1)
    start_date: date
    end_date: date
    initial_capital: Decimal = Field(default=Decimal("100000.0000"), gt=Decimal("0.0"))
    
    cost_profile_name: str = Field(default="zerodha_equity_delivery")
    slippage: SlippageConfig = Field(default_factory=SlippageConfig)
    benchmark: BenchmarkSymbol = Field(default=BenchmarkSymbol.NIFTY_50)
    
    validation_method: ValidationMethod = Field(default=ValidationMethod.standard)
    walk_forward_config: WalkForwardConfig | None = None
    
    random_seed: int = Field(default=42)


class BacktestTradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    backtest_id: uuid.UUID
    order_id: uuid.UUID
    fill_id: uuid.UUID
    signal_id: uuid.UUID | None
    strategy_id: str
    instrument_id: uuid.UUID
    symbol: str
    side: str
    quantity: Decimal
    execution_price: Decimal
    slippage: Decimal
    total_fees: Decimal
    fee_breakdown: dict[str, Any]
    realized_pnl: Decimal
    return_pct: Decimal
    risk_verdict_token: str | None
    executed_at: datetime


class BacktestResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    backtest_id: uuid.UUID
    segment_type: BacktestSegmentType
    segment_index: int
    segment_start: date | None
    segment_end: date | None
    metrics: dict[str, Any]
    equity_curve: list[dict[str, Any]] | None
    underwater_curve: list[dict[str, Any]] | None
    trade_count: int


class BacktestSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    strategy_id: str
    strategy_version: str
    status: BacktestStatus
    random_seed: int
    start_date: date
    end_date: date
    initial_capital: Decimal
    config_snapshot: dict[str, Any]
    error: str | None
    created_at: datetime
    results: list[BacktestResultResponse] = Field(default_factory=list)
    trades: list[BacktestTradeResponse] = Field(default_factory=list)


class MonteCarloSimulationResponse(BaseModel):
    backtest_id: uuid.UUID
    iterations: int
    random_seed: int
    terminal_equity_quantiles: dict[str, Decimal]
    max_drawdown_quantiles: dict[str, Decimal]
    sharpe_quantiles: dict[str, Decimal]
    probability_of_ruin: Decimal
    var_95: Decimal
    cvar_95: Decimal
    simulated_equity_paths: list[list[float]] | None = None
