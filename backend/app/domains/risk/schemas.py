"""Risk domain Pydantic schemas for API requests, responses, and rule results."""
from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.domains.risk.enums import BreakerState, RiskDecision, RuleType, ScopeType


class RiskLimitBase(BaseModel):
    """Base fields for risk limit configurations."""
    max_daily_loss_pct: Decimal = Field(default=Decimal("0.5000"), ge=0, le=1)
    max_drawdown_pct: Decimal = Field(default=Decimal("0.5000"), ge=0, le=1)
    per_trade_risk_pct: Decimal = Field(default=Decimal("1.0000"), ge=0, le=1)
    max_portfolio_heat_pct: Decimal = Field(default=Decimal("1.0000"), ge=0, le=1)
    max_open_positions: int = Field(default=100, ge=1, le=1000)
    max_instrument_exposure_pct: Decimal = Field(default=Decimal("1.0000"), ge=0, le=1)
    max_sector_exposure_pct: Decimal = Field(default=Decimal("1.0000"), ge=0, le=1)
    max_position_correlation: Decimal = Field(default=Decimal("0.9500"), ge=0, le=1)
    max_order_notional: Decimal | None = Field(default=None, ge=0)
    max_symbol_volatility: Decimal | None = Field(default=None, ge=0)
    max_orders_per_minute: int = Field(default=1000, ge=1, le=10000)
    is_active: bool = True


class RiskLimitCreate(RiskLimitBase):
    portfolio_id: uuid.UUID


class RiskLimitUpdate(BaseModel):
    max_daily_loss_pct: Decimal | None = Field(default=None, ge=0, le=1)
    max_drawdown_pct: Decimal | None = Field(default=None, ge=0, le=1)
    per_trade_risk_pct: Decimal | None = Field(default=None, ge=0, le=1)
    max_portfolio_heat_pct: Decimal | None = Field(default=None, ge=0, le=1)
    max_open_positions: int | None = Field(default=None, ge=1, le=1000)
    max_instrument_exposure_pct: Decimal | None = Field(default=None, ge=0, le=1)
    max_sector_exposure_pct: Decimal | None = Field(default=None, ge=0, le=1)
    max_position_correlation: Decimal | None = Field(default=None, ge=0, le=1)
    max_order_notional: Decimal | None = Field(default=None, ge=0)
    max_symbol_volatility: Decimal | None = Field(default=None, ge=0)
    max_orders_per_minute: int | None = Field(default=None, ge=1, le=10000)
    is_active: bool | None = None


class RiskLimitResponse(RiskLimitBase):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RuleEvaluationResult(BaseModel):
    """Detailed result of an individual risk rule check."""
    rule: str
    decision: RiskDecision
    observed_value: str | None = None
    threshold_value: str | None = None
    detail: str | None = None


class RiskVerdict(BaseModel):
    """Aggregate verdict issued by the pre-trade Risk Engine for an order."""
    decision: RiskDecision
    verdict_token: str
    order_id: uuid.UUID
    portfolio_id: uuid.UUID
    timestamp: datetime
    rule_results: list[RuleEvaluationResult] = []
    blocking_rule: str | None = None
    reason: str | None = None


class KillSwitchTripRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    activated_by: str = Field(default="user", min_length=1, max_length=64)


class KillSwitchResetRequest(BaseModel):
    reset_reason: str = Field(..., min_length=3, max_length=500)
    reset_by: str = Field(default="user", min_length=1, max_length=64)


class KillSwitchResponse(BaseModel):
    id: uuid.UUID
    scope: ScopeType
    scope_id: str | None
    is_active: bool
    reason: str | None
    activated_by: str | None
    activated_at: datetime | None
    reset_by: str | None
    reset_at: datetime | None
    reset_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CircuitBreakerResponse(BaseModel):
    id: uuid.UUID
    scope: ScopeType
    scope_id: str | None
    state: BreakerState
    cooloff_until: datetime | None
    trip_count: int
    last_tripped_at: datetime | None
    reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RiskEventResponse(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    order_id: uuid.UUID | None
    rule: str
    decision: RiskDecision
    observed_value: str | None
    threshold_value: str | None
    detail: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RiskStatusSummary(BaseModel):
    portfolio_id: uuid.UUID
    current_equity: Decimal
    peak_equity: Decimal
    current_drawdown_pct: Decimal
    today_realized_pnl: Decimal
    today_unrealized_pnl: Decimal
    open_positions_count: int
    gross_exposure: Decimal
    net_exposure: Decimal
    kill_switch_active: bool
    active_circuit_breakers_count: int
    timestamp: datetime
