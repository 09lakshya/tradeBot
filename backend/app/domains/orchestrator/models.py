"""SQLAlchemy ORM models for the Execution Orchestrator domain."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ExecutionCycleRecord(Base):
    """Stores full audit history and performance metrics for each orchestrator execution cycle."""
    __tablename__ = "orchestrator_execution_cycles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    mode: Mapped[str] = mapped_column(String(32), default="paper", nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Counts across pipeline stages
    signals_evaluated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_orders_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_approved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_submitted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_filled_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Detailed stage latencies in ms (e.g., {"market_data": 1.2, "strategy": 4.5, "portfolio": 3.1, ...})
    stage_latencies: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Status: success, partial_failure, failed, skipped_market_closed
    status: Mapped[str] = mapped_column(String(32), default="success", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TradingSessionRecord(Base):
    """Maintains an auditable log of market trading sessions and holiday statuses."""
    __tablename__ = "orchestrator_trading_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE", nullable=False, index=True)
    session_state: Mapped[str] = mapped_column(String(32), nullable=False)
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_half_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    special_session_notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


class OrchestratorEventRecord(Base):
    """Append-only store for immutable domain events emitted across the internal event bus."""
    __tablename__ = "orchestrator_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(64), default="ExecutionOrchestrator", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class InvariantCheckRecord(Base):
    """Audit log of continuous invariant checks, ledger reconciliations, and consistency reports."""
    __tablename__ = "orchestrator_invariant_checks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orchestrator_execution_cycles.id"),
        nullable=True,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    cash_reconciled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ledger_balanced: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    positions_consistent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    risk_audit_consistent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    all_passed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    discrepancy_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
