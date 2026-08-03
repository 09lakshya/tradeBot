"""Risk domain: per-portfolio limits, per-decision audit trail, and kill switch.

Every order passes through the risk engine; each rule evaluation is recorded here
so a rejection (or approval) is always explainable and auditable (spec §13).
"""
import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk


class RiskLimit(UUIDPk, Timestamps, Base):
    """Configurable safety envelope for a portfolio. Sensible defaults; capital-first."""
    __tablename__ = "risk_limits"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), unique=True, index=True
    )
    max_daily_loss_pct: Mapped[float] = mapped_column(Numeric(6, 4), default=0.02)      # 2%
    max_drawdown_pct: Mapped[float] = mapped_column(Numeric(6, 4), default=0.15)        # 15%
    per_trade_risk_pct: Mapped[float] = mapped_column(Numeric(6, 4), default=0.01)      # 1%
    max_portfolio_heat_pct: Mapped[float] = mapped_column(Numeric(6, 4), default=0.06)  # 6%
    max_open_positions: Mapped[int] = mapped_column(default=10)
    max_sector_exposure_pct: Mapped[float] = mapped_column(Numeric(6, 4), default=0.30)
    max_position_correlation: Mapped[float] = mapped_column(Numeric(5, 4), default=0.80)
    max_symbol_volatility: Mapped[float | None] = mapped_column(Numeric(10, 6))


class RiskDecision(str, enum.Enum):
    passed = "passed"
    blocked = "blocked"


class RiskEvent(UUIDPk, Timestamps, Base):
    """One row per rule check in the pre-trade gate — the risk audit trail."""
    __tablename__ = "risk_events"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"), index=True)
    rule: Mapped[str] = mapped_column(String(80))                 # e.g. "max_open_positions"
    decision: Mapped[RiskDecision] = mapped_column(Enum(RiskDecision))
    detail: Mapped[str | None] = mapped_column(Text)             # measured vs. limit


class KillSwitch(UUIDPk, Timestamps, Base):
    """When active, all new orders are blocked for the portfolio (emergency stop)."""
    __tablename__ = "kill_switches"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), unique=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    activated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
