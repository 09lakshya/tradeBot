"""Metrics domain: equity curve snapshots (hypertable) + computed performance metrics."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk


class EquitySnapshot(Base):
    """Point-in-time portfolio equity for the equity curve. TimescaleDB hypertable.

    Composite PK (portfolio_id, ts).
    """
    __tablename__ = "equity_snapshots"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    equity: Mapped[float] = mapped_column(Numeric(20, 4))
    cash: Mapped[float] = mapped_column(Numeric(20, 4))
    positions_value: Mapped[float] = mapped_column(Numeric(20, 4))
    drawdown_pct: Mapped[float] = mapped_column(Numeric(8, 5), default=0)


class MetricPeriod(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    inception = "inception"


class PerformanceMetric(UUIDPk, Timestamps, Base):
    """Aggregated performance for a portfolio over a period (spec §7)."""
    __tablename__ = "performance_metrics"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    period: Mapped[MetricPeriod] = mapped_column(Enum(MetricPeriod))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    total_return_pct: Mapped[float | None] = mapped_column(Numeric(12, 6))
    cagr: Mapped[float | None] = mapped_column(Numeric(12, 6))
    sharpe: Mapped[float | None] = mapped_column(Numeric(10, 4))
    sortino: Mapped[float | None] = mapped_column(Numeric(10, 4))
    max_drawdown_pct: Mapped[float | None] = mapped_column(Numeric(10, 5))
    win_rate: Mapped[float | None] = mapped_column(Numeric(6, 4))
    profit_factor: Mapped[float | None] = mapped_column(Numeric(10, 4))
    expectancy: Mapped[float | None] = mapped_column(Numeric(18, 4))
    avg_profit: Mapped[float | None] = mapped_column(Numeric(18, 4))
    avg_loss: Mapped[float | None] = mapped_column(Numeric(18, 4))
    benchmark_return_pct: Mapped[float | None] = mapped_column(Numeric(12, 6))  # vs NIFTY 50
