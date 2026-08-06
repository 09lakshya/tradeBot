"""SQLAlchemy ORM models for the Analytics domain.

Tables:
- TradeJournalEntry: Immutable round-trip trade records with full cost decomposition.
- EquitySnapshot: Time-series equity curve points for gross and net equity.
- AnalyticsAlert: Operational alerts triggered by threshold breaches.
- CostProfileRecord: Versioned, persistent trading cost profile storage.
"""
from __future__ import annotations

import uuid
from datetime import datetime, UTC
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk
from app.domains.analytics.enums import AlertSeverity, AlertType, ExitReason


class TradeJournalEntry(UUIDPk, Timestamps, Base):
    """Immutable record of a completed round-trip trade with full cost decomposition."""

    __tablename__ = "trade_journal_entries"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"), index=True)

    trade_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    strategy_id: Mapped[str] = mapped_column(String(100), index=True)
    strategy_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    parameter_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    symbol: Mapped[str] = mapped_column(String(50), index=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)

    entry_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    exit_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    exit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))

    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    position_size_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0.0000"))
    holding_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)

    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    exit_reason: Mapped[ExitReason] = mapped_column(
        Enum(ExitReason, native_enum=False, length=30),
        default=ExitReason.unknown,
    )
    signal_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.0000"))

    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)

    # P&L fields
    gross_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    gross_return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"))
    net_return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"))

    # Excursion analysis
    mfe: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    mae: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))

    # Cost decomposition (JSON for extensibility)
    cost_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_profile_version: Mapped[str] = mapped_column(String(100), default="default")

    # Market regime at trade time
    market_regime: Mapped[str] = mapped_column(String(50), default="unknown")

    # Snapshot references
    portfolio_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    entry_order_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    exit_order_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # Configuration snapshot for version tracking
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_journal_portfolio_entry", "portfolio_id", "entry_timestamp"),
        Index("ix_journal_portfolio_exit", "portfolio_id", "exit_timestamp"),
        Index("ix_journal_strategy_symbol", "strategy_id", "symbol"),
    )


class EquitySnapshot(UUIDPk, Timestamps, Base):
    """Time-series equity curve data point for gross and net portfolio equity."""

    __tablename__ = "analytics_equity_snapshots"


    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    gross_equity: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    net_equity: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    invested_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))

    gross_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"))
    net_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"))

    daily_gross_return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.000000"))
    daily_net_return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.000000"))

    cost_profile_version: Mapped[str] = mapped_column(String(100), default="default")

    __table_args__ = (
        Index("ix_equity_portfolio_ts", "portfolio_id", "timestamp"),
    )


class AnalyticsAlert(UUIDPk, Timestamps, Base):
    """Operational alert triggered by threshold breaches."""

    __tablename__ = "analytics_alerts"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, native_enum=False, length=40),
        index=True,
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, native_enum=False, length=20),
        default=AlertSeverity.info,
    )
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(String(1000))
    metric_name: Mapped[str] = mapped_column(String(100))
    metric_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    strategy_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_alerts_portfolio_created", "portfolio_id", "created_at"),
    )


class CostProfileRecord(UUIDPk, Timestamps, Base):
    """Versioned, persistent trading cost profile."""

    __tablename__ = "cost_profiles"

    profile_name: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[str] = mapped_column(String(30))
    profile_data: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(String(500), default="")

    __table_args__ = (
        UniqueConstraint("profile_name", "version", name="uq_cost_profile_name_version"),
    )
