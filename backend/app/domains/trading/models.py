"""Trading domain database models.

Includes:
- Portfolio (with cash balance, reserved cash, optimistic versioning)
- Order (strict state tracking, idempotency, Decimal precision)
- OrderDecision (AI/strategy explainability audit trail)
- Fill (execution records with exact Indian statutory cost breakdowns)
- Position (holdings, average price, realized/unrealized P&L)
- PositionLot (FIFO lot accounting for cost basis & tax accuracy)
- Transaction (immutable append-only cash ledger)
- OrderEventLog (immutable event log for deterministic audit & replay)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk
from app.domains.trading.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    ProductType,
    TimeInForce,
    TradingMode,
    TxnType,
)


class Portfolio(UUIDPk, Timestamps, Base):
    """Trading account portfolio with cash balance and reserved buying power."""

    __tablename__ = "portfolios"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    mode: Mapped[TradingMode] = mapped_column(
        Enum(TradingMode, native_enum=False, length=20),
        default=TradingMode.paper,
    )
    base_currency: Mapped[str] = mapped_column(String(10), default="INR")
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    reserved_cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    version: Mapped[int] = mapped_column(Integer, default=1)

    orders: Mapped[list[Order]] = relationship("Order", back_populates="portfolio", cascade="all, delete-orphan")
    positions: Mapped[list[Position]] = relationship("Position", back_populates="portfolio", cascade="all, delete-orphan")
    transactions: Mapped[list[Transaction]] = relationship("Transaction", back_populates="portfolio", cascade="all, delete-orphan")


class Order(UUIDPk, Timestamps, Base):
    """Order submitted to the OMS."""

    __tablename__ = "orders"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide, native_enum=False, length=10))
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType, native_enum=False, length=20))
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType, native_enum=False, length=10),
        default=ProductType.cnc,
    )
    time_in_force: Mapped[TimeInForce] = mapped_column(
        Enum(TimeInForce, native_enum=False, length=10),
        default=TimeInForce.day,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False, length=20),
        default=OrderStatus.created,
        index=True,
    )
    reserved_cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    rejected_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="orders")
    decision: Mapped[OrderDecision | None] = relationship("OrderDecision", back_populates="order", uselist=False, cascade="all, delete-orphan")
    fills: Mapped[list[Fill]] = relationship("Fill", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_orders_portfolio_status", "portfolio_id", "status"),
    )


class OrderDecision(UUIDPk, Timestamps, Base):
    """Explainability record required for every trade order."""

    __tablename__ = "order_decisions"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    model_confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    expected_return: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    market_regime: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entry_reason: Mapped[str] = mapped_column(String(500))
    exit_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str] = mapped_column(String(1000))
    raw_signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    order: Mapped[Order] = relationship("Order", back_populates="decision")


class Fill(UUIDPk, Timestamps, Base):
    """Execution fill with full Indian market statutory fee decomposition."""

    __tablename__ = "fills"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    fill_sequence: Mapped[int] = mapped_column(Integer, default=1)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    slippage: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    brokerage: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    stt: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    exchange_charges: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    gst: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    stamp_duty: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    sebi_charges: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    total_charges: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    order: Mapped[Order] = relationship("Order", back_populates="fills")


class Position(UUIDPk, Timestamps, Base):
    """Open or closed position holding for an instrument in a portfolio."""

    __tablename__ = "positions"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType, native_enum=False, length=10),
        default=ProductType.cnc,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    status: Mapped[PositionStatus] = mapped_column(
        Enum(PositionStatus, native_enum=False, length=10),
        default=PositionStatus.open,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)

    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="positions")
    lots: Mapped[list[PositionLot]] = relationship("PositionLot", back_populates="position", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("portfolio_id", "instrument_id", "product_type", name="uq_portfolio_instrument_product"),
    )


class PositionLot(UUIDPk, Timestamps, Base):
    """FIFO Lot for tracking tax and cost basis of shares purchased in tranches."""

    __tablename__ = "position_lots"

    position_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("positions.id"), index=True)
    fill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fills.id"))
    initial_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    position: Mapped[Position] = relationship("Position", back_populates="lots")

    __table_args__ = (
        Index("ix_position_lots_active", "position_id", "remaining_quantity"),
    )


class Transaction(UUIDPk, Timestamps, Base):
    """Immutable double-entry append-only cash ledger."""

    __tablename__ = "transactions"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    txn_type: Mapped[TxnType] = mapped_column(Enum(TxnType, native_enum=False, length=30))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))  # + for credit, - for debit
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    related_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    related_fill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fills.id"), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_portfolio_created", "portfolio_id", "created_at"),
    )


class OrderEventLog(UUIDPk, Base):
    """Immutable event stream for deterministic replay and auditability."""

    __tablename__ = "order_event_logs"

    event_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(index=True)
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_version: Mapped[int] = mapped_column(Integer, default=1)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(index=True)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_event_log_agg_ver", "aggregate_id", "aggregate_version"),
    )
