"""Position manager with FIFO lot accounting and realized/unrealized P&L calculations."""
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.trading.clock import Clock
from app.domains.trading.enums import OrderSide, PositionStatus, ProductType
from app.domains.trading.events import (
    DomainEvent,
    PositionClosedEvent,
    PositionOpenedEvent,
    PositionUpdatedEvent,
)
from app.domains.trading.exceptions import (
    InsufficientPositionQuantityError,
)
from app.domains.trading.models import Fill, Position, PositionLot

DEC_4DP = Decimal("0.0001")


def _quantize(val: Decimal) -> Decimal:
    return val.quantize(DEC_4DP, rounding=ROUND_HALF_UP)


class PositionManager:
    """Manages open/closed positions, FIFO lot depletions, and P&L tracking."""

    def __init__(self, db: Session, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    def get_position(
        self,
        portfolio_id: uuid.UUID,
        instrument_id: uuid.UUID,
        product_type: ProductType = ProductType.cnc,
    ) -> Position | None:
        """Fetch position record if it exists."""
        stmt = select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.instrument_id == instrument_id,
            Position.product_type == product_type,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_portfolio_positions(self, portfolio_id: uuid.UUID) -> list[Position]:
        """Fetch all positions belonging to a portfolio."""
        stmt = select(Position).where(Position.portfolio_id == portfolio_id)
        return list(self._db.execute(stmt).scalars().all())

    def get_or_create_position(
        self,
        portfolio_id: uuid.UUID,
        instrument_id: uuid.UUID,
        product_type: ProductType = ProductType.cnc,
    ) -> Position:
        """Fetch existing position or create a new empty one."""
        pos = self.get_position(portfolio_id, instrument_id, product_type)
        if pos is None:
            pos = Position(
                portfolio_id=portfolio_id,
                instrument_id=instrument_id,
                product_type=product_type,
                quantity=Decimal("0.0000"),
                avg_entry_price=Decimal("0.0000"),
                current_price=Decimal("0.0000"),
                unrealized_pnl=Decimal("0.0000"),
                realized_pnl=Decimal("0.0000"),
                status=PositionStatus.open,
            )
            self._db.add(pos)
            self._db.flush()
        return pos

    def apply_fill(
        self,
        fill: Fill,
        side: OrderSide,
        product_type: ProductType = ProductType.cnc,
        correlation_id: uuid.UUID | None = None,
    ) -> tuple[Position, list[DomainEvent]]:
        """Apply fill execution to position with FIFO lot accounting."""
        events: list[DomainEvent] = []
        corr_id = correlation_id or uuid.uuid4()

        if side == OrderSide.buy:
            pos = self.get_or_create_position(fill.portfolio_id, fill.instrument_id, product_type)
            is_new = pos.quantity == Decimal("0.0000") or pos.status == PositionStatus.closed

            old_qty = pos.quantity if pos.status == PositionStatus.open else Decimal("0.0000")
            old_cost = old_qty * pos.avg_entry_price
            fill_cost = fill.quantity * fill.price
            new_qty = old_qty + fill.quantity
            new_avg = (old_cost + fill_cost) / new_qty

            pos.quantity = _quantize(new_qty)
            pos.avg_entry_price = _quantize(new_avg)
            pos.current_price = _quantize(fill.price)
            pos.unrealized_pnl = Decimal("0.0000")
            pos.status = PositionStatus.open
            pos.version += 1

            # Record FIFO Lot
            lot = PositionLot(
                position_id=pos.id,
                fill_id=fill.id,
                initial_quantity=fill.quantity,
                remaining_quantity=fill.quantity,
                price=fill.price,
                opened_at=self._clock.now(),
            )
            self._db.add(lot)
            self._db.flush()

            evt_cls = PositionOpenedEvent if is_new else PositionUpdatedEvent
            events.append(
                evt_cls(
                    aggregate_id=pos.id,
                    aggregate_version=pos.version,
                    correlation_id=corr_id,
                    payload={
                        "position_id": str(pos.id),
                        "portfolio_id": str(pos.portfolio_id),
                        "instrument_id": str(pos.instrument_id),
                        "quantity": str(pos.quantity),
                        "avg_entry_price": str(pos.avg_entry_price),
                        "side": side.value,
                    },
                )
            )

        elif side == OrderSide.sell:
            pos = self.get_position(fill.portfolio_id, fill.instrument_id, product_type)
            if pos is None or pos.status == PositionStatus.closed or pos.quantity < fill.quantity:
                available = pos.quantity if pos else Decimal("0.0000")
                raise InsufficientPositionQuantityError(
                    portfolio_id=fill.portfolio_id,
                    instrument_id=fill.instrument_id,
                    requested=fill.quantity,
                    available=available,
                )

            # Fetch active FIFO lots chronologically
            stmt = (
                select(PositionLot)
                .where(PositionLot.position_id == pos.id, PositionLot.remaining_quantity > Decimal("0.0000"))
                .order_by(PositionLot.opened_at.asc(), PositionLot.created_at.asc())
            )
            active_lots = list(self._db.execute(stmt).scalars().all())

            remaining_to_sell = fill.quantity
            gross_realized_pnl = Decimal("0.0000")

            for lot in active_lots:
                if remaining_to_sell <= Decimal("0.0000"):
                    break
                deplete_qty = min(lot.remaining_quantity, remaining_to_sell)
                lot_pnl = (fill.price - lot.price) * deplete_qty
                gross_realized_pnl += lot_pnl
                lot.remaining_quantity -= deplete_qty
                remaining_to_sell -= deplete_qty

            # Deduct fill charges from realized P&L
            net_realized_pnl = gross_realized_pnl - fill.total_charges
            pos.realized_pnl += _quantize(net_realized_pnl)
            new_qty = pos.quantity - fill.quantity
            pos.quantity = _quantize(new_qty)
            pos.current_price = _quantize(fill.price)
            pos.version += 1

            if pos.quantity == Decimal("0.0000"):
                pos.status = PositionStatus.closed
                pos.avg_entry_price = Decimal("0.0000")
                pos.unrealized_pnl = Decimal("0.0000")
                events.append(
                    PositionClosedEvent(
                        aggregate_id=pos.id,
                        aggregate_version=pos.version,
                        correlation_id=corr_id,
                        payload={
                            "position_id": str(pos.id),
                            "portfolio_id": str(pos.portfolio_id),
                            "instrument_id": str(pos.instrument_id),
                            "realized_pnl": str(pos.realized_pnl),
                        },
                    )
                )
            else:
                # Recalculate average entry price from remaining active lots
                remaining_active_stmt = (
                    select(PositionLot)
                    .where(PositionLot.position_id == pos.id, PositionLot.remaining_quantity > Decimal("0.0000"))
                )
                remaining_lots = list(self._db.execute(remaining_active_stmt).scalars().all())
                total_cost = sum(l.remaining_quantity * l.price for l in remaining_lots)
                pos.avg_entry_price = _quantize(total_cost / pos.quantity)
                pos.unrealized_pnl = _quantize((pos.current_price - pos.avg_entry_price) * pos.quantity)
                events.append(
                    PositionUpdatedEvent(
                        aggregate_id=pos.id,
                        aggregate_version=pos.version,
                        correlation_id=corr_id,
                        payload={
                            "position_id": str(pos.id),
                            "portfolio_id": str(pos.portfolio_id),
                            "instrument_id": str(pos.instrument_id),
                            "quantity": str(pos.quantity),
                            "avg_entry_price": str(pos.avg_entry_price),
                            "side": side.value,
                            "realized_pnl": str(pos.realized_pnl),
                        },
                    )
                )

        self._db.flush()
        return pos, events

    def update_market_price(self, position: Position, market_price: Decimal) -> None:
        """Mark position to market with latest price."""
        position.current_price = _quantize(market_price)
        if position.status == PositionStatus.open and position.quantity > Decimal("0.0000"):
            position.unrealized_pnl = _quantize((market_price - position.avg_entry_price) * position.quantity)
        else:
            position.unrealized_pnl = Decimal("0.0000")
