"""SQLAlchemy Database Models for Strategy Engine."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db import Base
from app.domains.strategies.enums import (
    MarketRegime,
    SignalDirection,
    SignalType,
    StrategyCategory,
    StrategyStatus,
)

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class StrategyDefinition(Base):
    """Registered strategy definition and version metadata."""
    __tablename__ = "strategy_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    category: Mapped[StrategyCategory] = mapped_column(
        Enum(StrategyCategory, name="strategy_category_enum"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author: Mapped[str] = mapped_column(String(100), default="Quantitative Research Team", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class StrategyParameterSnapshot(Base):
    """Immutable versioned parameter snapshot for reproducible strategy execution."""
    __tablename__ = "strategy_parameter_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_strat_param_lookup", "strategy_id", "version"),
    )


class StrategyInstance(Base):
    """An active or historical instance of a strategy attached to a portfolio."""
    __tablename__ = "strategy_instances"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    custom_name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[StrategyStatus] = mapped_column(
        Enum(StrategyStatus, name="strategy_status_enum"),
        default=StrategyStatus.active,
        nullable=False,
        index=True,
    )
    parameter_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_parameter_snapshots.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SignalRecord(Base):
    """Persistent audit record of an explainable trading signal."""
    __tablename__ = "strategy_signals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    strategy_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    signal_type: Mapped[SignalType] = mapped_column(
        Enum(SignalType, name="signal_type_enum"),
        nullable=False,
    )
    direction: Mapped[SignalDirection] = mapped_column(
        Enum(SignalDirection, name="signal_direction_enum"),
        nullable=False,
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("1.0000"))
    target_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    market_regime: Mapped[MarketRegime] = mapped_column(
        Enum(MarketRegime, name="market_regime_enum"),
        nullable=False,
        default=MarketRegime.unknown,
    )
    supporting_indicators: Mapped[dict] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    generation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_signal_symbol_ts", "symbol", "timestamp"),
        Index("ix_signal_strategy_ts", "strategy_id", "timestamp"),
    )


# Model Aliases for consistent naming
StrategyModel = StrategyDefinition
StrategyParameterSnapshotModel = StrategyParameterSnapshot
StrategySignalModel = SignalRecord
