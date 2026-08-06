"""Portfolio Construction Domain ORM Models for Auditing and Historical Replay."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk
from app.domains.portfolio.enums import (
    AllocationPolicyType,
    ArbitrationMethod,
    CandidateOrderStatus,
    SizingMethod,
)
from app.domains.trading.enums import OrderSide, ProductType


class PortfolioConstructionPlan(UUIDPk, Timestamps, Base):
    """Execution record for a portfolio construction cycle."""
    __tablename__ = "portfolio_construction_plans"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    allocation_policy: Mapped[str] = mapped_column(String(50), nullable=False)
    sizing_method: Mapped[str] = mapped_column(String(50), nullable=False)
    total_equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash_allocated: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reserve_cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    summary_metrics: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)

    candidate_orders: Mapped[list["CandidateOrderRecord"]] = relationship(
        "CandidateOrderRecord", back_populates="plan", cascade="all, delete-orphan"
    )
    arbitration_records: Mapped[list["ArbitrationAuditRecord"]] = relationship(
        "ArbitrationAuditRecord", back_populates="plan", cascade="all, delete-orphan"
    )


class CandidateOrderRecord(UUIDPk, Timestamps, Base):
    """Audit record of an immutable candidate order produced by the engine."""
    __tablename__ = "candidate_order_records"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_construction_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    product_type: Mapped[str] = mapped_column(String(20), default="cnc", nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    target_weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    current_weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0.0000"), nullable=False)
    estimated_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    estimated_notional: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    expected_return: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    expected_risk: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    strategy_sources: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    signal_sources: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    scoring_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    sizing_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    transaction_costs_json: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    explainability_trace: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="generated", nullable=False)

    plan: Mapped["PortfolioConstructionPlan"] = relationship(
        "PortfolioConstructionPlan", back_populates="candidate_orders"
    )

    __table_args__ = (
        Index("ix_cand_order_plan_symbol", "plan_id", "symbol"),
    )


class ArbitrationAuditRecord(UUIDPk, Timestamps, Base):
    """Audit trail of signal arbitration resolutions per instrument."""
    __tablename__ = "arbitration_audit_records"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_construction_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resolution_method: Mapped[str] = mapped_column(String(50), nullable=False)
    input_signals: Mapped[list[dict[str, Any]]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    winning_signal: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    explainability: Mapped[str] = mapped_column(Text, nullable=False)

    plan: Mapped["PortfolioConstructionPlan"] = relationship(
        "PortfolioConstructionPlan", back_populates="arbitration_records"
    )
