"""Immutable RiskSnapshot and builder for pre-trade risk evaluation."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.market_data.models import Instrument
from app.domains.risk.enums import BreakerState, ScopeType
from app.domains.risk.models import CircuitBreaker, KillSwitch, RiskLimit
from app.domains.trading.clock import Clock
from app.domains.trading.models import Order, Portfolio, Position


@dataclass(frozen=True)
class PositionRiskSnapshot:
    """Immutable view of a single open position at risk evaluation time."""
    instrument_id: uuid.UUID
    symbol: str
    sector: str | None
    quantity: Decimal
    average_entry_price: Decimal
    current_market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    stop_loss_price: Decimal | None = None


@dataclass(frozen=True)
class BreakerSnapshot:
    """Immutable view of a circuit breaker."""
    scope: ScopeType
    scope_id: str | None
    state: BreakerState
    cooloff_until: datetime | None
    reason: str | None


@dataclass(frozen=True)
class RiskSnapshot:
    """Complete, immutable snapshot of portfolio state passed to pure risk rules."""
    portfolio_id: uuid.UUID
    cash_balance: Decimal
    reserved_cash: Decimal
    available_buying_power: Decimal
    current_equity: Decimal
    peak_equity: Decimal
    today_realized_pnl: Decimal
    today_unrealized_pnl: Decimal
    open_positions: dict[uuid.UUID, PositionRiskSnapshot]
    recent_order_count: int
    is_kill_switch_active: bool
    kill_switch_reason: str | None
    active_breakers: tuple[BreakerSnapshot, ...]
    volatilities: dict[uuid.UUID, Decimal]
    correlations: dict[tuple[uuid.UUID, uuid.UUID], Decimal]
    sector_mappings: dict[uuid.UUID, str]
    limits: RiskLimit
    timestamp: datetime


class RiskSnapshotBuilder:
    """Constructs an immutable RiskSnapshot from database state and live market prices."""

    def __init__(self, db: Session, clock: Clock):
        self.db = db
        self.clock = clock

    def build_snapshot(
        self,
        portfolio_id: uuid.UUID,
        market_prices: dict[uuid.UUID, Decimal] | None = None,
        volatilities: dict[uuid.UUID, Decimal] | None = None,
        correlations: dict[tuple[uuid.UUID, uuid.UUID], Decimal] | None = None,
    ) -> RiskSnapshot:
        now = self.clock.now()
        market_prices = market_prices or {}
        volatilities = volatilities or {}
        correlations = correlations or {}

        # 1. Fetch Portfolio
        port = self.db.get(Portfolio, portfolio_id)
        if not port:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        cash_balance = port.cash_balance
        reserved_cash = port.reserved_cash
        available_bp = cash_balance - reserved_cash

        # 2. Fetch or create default RiskLimits
        limits = self.db.execute(
            select(RiskLimit).where(RiskLimit.portfolio_id == portfolio_id)
        ).scalar_one_or_none()

        if not limits:
            limits = RiskLimit(portfolio_id=portfolio_id)
            self.db.add(limits)
            self.db.flush()

        # 3. Fetch Positions & Instruments
        positions = self.db.execute(
            select(Position).where(
                Position.portfolio_id == portfolio_id,
                Position.quantity != Decimal("0.0000"),
            )
        ).scalars().all()

        open_positions: dict[uuid.UUID, PositionRiskSnapshot] = {}
        sector_mappings: dict[uuid.UUID, str] = {}
        total_market_value = Decimal("0.0000")
        today_unrealized_pnl = Decimal("0.0000")
        today_realized_pnl = Decimal("0.0000")

        for pos in positions:
            inst = self.db.get(Instrument, pos.instrument_id)
            symbol = inst.trading_symbol if inst else str(pos.instrument_id)
            sector = inst.industry or inst.sector if inst else None
            sector_mappings[pos.instrument_id] = sector or "Unknown"

            cur_price = market_prices.get(pos.instrument_id, pos.avg_entry_price)
            mv = (pos.quantity * cur_price).quantize(Decimal("0.0001"))
            cost_basis = (pos.quantity * pos.avg_entry_price).quantize(Decimal("0.0001"))
            unrealized = mv - cost_basis

            total_market_value += mv
            today_unrealized_pnl += unrealized
            today_realized_pnl += pos.realized_pnl

            open_positions[pos.instrument_id] = PositionRiskSnapshot(
                instrument_id=pos.instrument_id,
                symbol=symbol,
                sector=sector,
                quantity=pos.quantity,
                average_entry_price=pos.avg_entry_price,
                current_market_price=cur_price,
                market_value=mv,
                unrealized_pnl=unrealized,
                realized_pnl=pos.realized_pnl,
            )

        current_equity = cash_balance + total_market_value
        peak_equity = max(current_equity, cash_balance)  # Track or project peak equity

        # 4. Fetch Kill Switch State
        active_ks = self.db.execute(
            select(KillSwitch).where(
                KillSwitch.is_active == True,
                (
                    (KillSwitch.scope == ScopeType.global_scope)
                    | (
                        (KillSwitch.scope == ScopeType.portfolio)
                        & (KillSwitch.scope_id == str(portfolio_id))
                    )
                ),
            )
        ).scalars().first()

        is_kill_switch_active = active_ks is not None
        kill_switch_reason = active_ks.reason if active_ks else None

        # 5. Fetch Active Circuit Breakers
        breakers = self.db.execute(
            select(CircuitBreaker).where(
                CircuitBreaker.state.in_([BreakerState.tripped, BreakerState.half_open]),
                (
                    (CircuitBreaker.scope == ScopeType.global_scope)
                    | (
                        (CircuitBreaker.scope == ScopeType.portfolio)
                        & (CircuitBreaker.scope_id == str(portfolio_id))
                    )
                ),
            )
        ).scalars().all()

        active_breakers_list = [
            BreakerSnapshot(
                scope=b.scope,
                scope_id=b.scope_id,
                state=b.state,
                cooloff_until=b.cooloff_until,
                reason=b.reason,
            )
            for b in breakers
        ]

        # 6. Fetch recent order velocity count (last 60 seconds)
        one_min_ago = now - timedelta(seconds=60)
        recent_order_count = self.db.execute(
            select(func.count(Order.id)).where(
                Order.portfolio_id == portfolio_id,
                Order.created_at >= one_min_ago,
            )
        ).scalar() or 0

        return RiskSnapshot(
            portfolio_id=portfolio_id,
            cash_balance=cash_balance,
            reserved_cash=reserved_cash,
            available_buying_power=available_bp,
            current_equity=current_equity,
            peak_equity=peak_equity,
            today_realized_pnl=today_realized_pnl,
            today_unrealized_pnl=today_unrealized_pnl,
            open_positions=open_positions,
            recent_order_count=recent_order_count,
            is_kill_switch_active=is_kill_switch_active,
            kill_switch_reason=kill_switch_reason,
            active_breakers=tuple(active_breakers_list),
            volatilities=volatilities,
            correlations=correlations,
            sector_mappings=sector_mappings,
            limits=limits,
            timestamp=now,
        )
