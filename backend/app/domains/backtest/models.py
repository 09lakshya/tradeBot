"""Backtest domain: backtest runs and their results (incl. walk-forward / OOS segments)."""
import enum
import uuid
from datetime import date

from sqlalchemy import JSON, Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk


class BacktestStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class Backtest(UUIDPk, Timestamps, Base):
    __tablename__ = "backtests"

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), index=True
    )
    instrument_ids: Mapped[list] = mapped_column(JSON)     # list of instrument UUIDs (str)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    initial_capital: Mapped[float] = mapped_column(Numeric(20, 4))
    params: Mapped[dict] = mapped_column(JSON)             # cost model, slippage bps, etc.
    status: Mapped[BacktestStatus] = mapped_column(
        Enum(BacktestStatus), default=BacktestStatus.queued, index=True
    )
    error: Mapped[str | None] = mapped_column(String(1000))


class BacktestSegmentType(str, enum.Enum):
    full = "full"
    in_sample = "in_sample"
    out_of_sample = "out_of_sample"
    walk_forward = "walk_forward"
    monte_carlo = "monte_carlo"


class BacktestResult(UUIDPk, Timestamps, Base):
    """Metrics for one segment of a backtest. Multiple rows per backtest support
    walk-forward windows and OOS/IS comparison — the anti-overfitting evidence."""
    __tablename__ = "backtest_results"

    backtest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtests.id"), index=True)
    segment_type: Mapped[BacktestSegmentType] = mapped_column(
        Enum(BacktestSegmentType), default=BacktestSegmentType.full
    )
    segment_start: Mapped[date | None] = mapped_column(Date)
    segment_end: Mapped[date | None] = mapped_column(Date)
    metrics: Mapped[dict] = mapped_column(JSON)            # sharpe, sortino, dd, pf, expectancy...
    equity_curve: Mapped[list | None] = mapped_column(JSON)  # [[ts, equity], ...] or storage ref
    trade_count: Mapped[int] = mapped_column(default=0)
