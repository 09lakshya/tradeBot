"""Risk domain ORM models: limits, rule audit trail, kill switch, and circuit breakers.

Every order passes through the mandatory pre-trade risk engine (ADR 0010).
All evaluations, verdicts, emergency trips, and breaker states are persisted here.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk
from app.domains.risk.enums import BreakerState, RiskDecision, ScopeType


class RiskLimit(UUIDPk, Timestamps, Base):
    """Configurable safety envelope and parameters for a portfolio."""
    __tablename__ = "risk_limits"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), unique=True, index=True
    )
    max_daily_loss_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.5000")
    )  # 50% default unconfigured
    max_drawdown_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.5000")
    )  # 50% default unconfigured
    per_trade_risk_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("1.0000")
    )  # 100% default unconfigured
    max_portfolio_heat_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("1.0000")
    )  # 100% default unconfigured
    max_open_positions: Mapped[int] = mapped_column(Integer, default=100)
    max_instrument_exposure_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("1.0000")
    )  # 100% default unconfigured
    max_sector_exposure_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("1.0000")
    )  # 100% default unconfigured
    max_position_correlation: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.9500")
    )  # 0.95 default
    max_order_notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    max_symbol_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    max_orders_per_minute: Mapped[int] = mapped_column(Integer, default=1000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RiskEvent(UUIDPk, Timestamps, Base):
    """Immutable audit trail row for an individual rule check in the pre-trade gate."""
    __tablename__ = "risk_events"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=True
    )
    rule: Mapped[str] = mapped_column(String(80), index=True)
    decision: Mapped[RiskDecision] = mapped_column(Enum(RiskDecision))
    observed_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    threshold_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_risk_events_portfolio_created", "portfolio_id", "created_at"),
    )


class KillSwitch(UUIDPk, Timestamps, Base):
    """Emergency master stop. When tripped, blocks new risk-increasing orders."""
    __tablename__ = "kill_switches"

    scope: Mapped[ScopeType] = mapped_column(
        Enum(ScopeType), default=ScopeType.portfolio
    )
    scope_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )  # portfolio_id or symbol or None for global
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reset_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reset_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_kill_switches_scope_lookup", "scope", "scope_id", "is_active"),
    )


class CircuitBreaker(UUIDPk, Timestamps, Base):
    """Automatic, self-resetting cooloff halt for volatility spikes or soft loss limits."""
    __tablename__ = "circuit_breakers"

    scope: Mapped[ScopeType] = mapped_column(
        Enum(ScopeType), default=ScopeType.portfolio
    )
    scope_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    state: Mapped[BreakerState] = mapped_column(
        Enum(BreakerState), default=BreakerState.armed, index=True
    )
    cooloff_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trip_count: Mapped[int] = mapped_column(Integer, default=0)
    last_tripped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_circuit_breakers_scope_state", "scope", "scope_id", "state"),
    )
