"""Backtest domain: persistent tables for backtest runs, results, trades, and pinned data snapshots."""
from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk
from app.domains.backtest.enums import BacktestSegmentType, BacktestStatus


class DataSnapshot(UUIDPk, Timestamps, Base):
    """Pinned dataset version capturing historical market data snapshot parameters."""
    __tablename__ = "data_snapshots"

    provider: Mapped[str] = mapped_column(String(50), default="mock")
    dataset_identifier: Mapped[str] = mapped_column(String(100), index=True)
    download_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    corporate_action_version: Mapped[str] = mapped_column(String(50), default="v1.0")
    benchmark_version: Mapped[str] = mapped_column(String(50), default="NIFTY_50_v1")
    instruments_count: Mapped[int] = mapped_column(default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Backtest(UUIDPk, Timestamps, Base):
    """Primary backtest execution run."""
    __tablename__ = "backtests"

    name: Mapped[str] = mapped_column(String(120), default="Backtest Run")
    strategy_id: Mapped[str] = mapped_column(String(100), index=True)
    strategy_version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("portfolios.id"), nullable=True, index=True)
    data_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_snapshots.id"), nullable=True, index=True)
    
    random_seed: Mapped[int] = mapped_column(default=42)
    instrument_ids: Mapped[list] = mapped_column(JSON)  # List of instrument UUID strings
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    
    # Complete configuration snapshot (risk profile, slippage model, cost profile, execution model)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    
    status: Mapped[BacktestStatus] = mapped_column(
        Enum(BacktestStatus), default=BacktestStatus.queued, index=True
    )
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Relationships
    results: Mapped[list["BacktestResult"]] = relationship("BacktestResult", back_populates="backtest", cascade="all, delete-orphan")
    trades: Mapped[list["BacktestTrade"]] = relationship("BacktestTrade", back_populates="backtest", cascade="all, delete-orphan")


class BacktestResult(UUIDPk, Timestamps, Base):
    """Metrics and equity curves for a specific segment of a backtest (IS, OOS, Walk-Forward, Monte Carlo)."""
    __tablename__ = "backtest_results"

    backtest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtests.id"), index=True)
    segment_type: Mapped[BacktestSegmentType] = mapped_column(
        Enum(BacktestSegmentType), default=BacktestSegmentType.full, index=True
    )
    segment_index: Mapped[int] = mapped_column(default=0)  # For walk-forward window index
    segment_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    segment_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Comprehensive performance metrics (Sharpe, Sortino, Calmar, MaxDD, DSR, PSR, PBO, WinRate, etc.)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Equity curve snapshot points: list of {"ts": str, "equity": float, "cash": float, "drawdown_pct": float}
    equity_curve: Mapped[list | None] = mapped_column(JSON, nullable=True)
    
    # Underwater drawdown curve points: list of {"ts": str, "drawdown_pct": float}
    underwater_curve: Mapped[list | None] = mapped_column(JSON, nullable=True)
    
    trade_count: Mapped[int] = mapped_column(default=0)

    backtest: Mapped["Backtest"] = relationship("Backtest", back_populates="results")


class BacktestTrade(UUIDPk, Timestamps, Base):
    """Full explainable and auditable trade executed during a backtest."""
    __tablename__ = "backtest_trades"

    backtest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtests.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(index=True)
    fill_id: Mapped[uuid.UUID] = mapped_column(index=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    strategy_id: Mapped[str] = mapped_column(String(100))
    instrument_id: Mapped[uuid.UUID] = mapped_column(index=True)
    symbol: Mapped[str] = mapped_column(String(50))
    
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    execution_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    slippage: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    
    total_fees: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    fee_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)  # brokerage, stt, gst, etc.
    
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0.0000"))
    return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.0000"))
    
    risk_verdict_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    backtest: Mapped["Backtest"] = relationship("Backtest", back_populates="trades")
