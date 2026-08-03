"""Deterministic event log replay engine.

Reconstructs exact portfolio, order, fill, and position states from an immutable event stream.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.domains.trading.models import OrderEventLog


@dataclass
class ReplayPosition:
    instrument_id: str
    quantity: Decimal = Decimal("0.0000")
    avg_entry_price: Decimal = Decimal("0.0000")
    realized_pnl: Decimal = Decimal("0.0000")
    status: str = "open"


@dataclass
class ReplayOrder:
    order_id: str
    instrument_id: str
    side: str
    order_type: str
    quantity: Decimal = Decimal("0.0000")
    filled_quantity: Decimal = Decimal("0.0000")
    limit_price: Decimal | None = None
    status: str = "created"
    rejected_reason: str | None = None


@dataclass
class ReplayFill:
    fill_id: str
    order_id: str
    quantity: Decimal
    price: Decimal
    total_charges: Decimal


@dataclass
class ReplayState:
    portfolio_id: str
    cash_balance: Decimal = Decimal("0.0000")
    reserved_cash: Decimal = Decimal("0.0000")
    positions: dict[str, ReplayPosition] = field(default_factory=dict)
    orders: dict[str, ReplayOrder] = field(default_factory=dict)
    fills: list[ReplayFill] = field(default_factory=list)
    events_processed: int = 0


class DeterministicReplayEngine:
    """Replays domain events to reconstruct state deterministically."""

    def __init__(self, portfolio_id: uuid.UUID) -> None:
        self.portfolio_id = str(portfolio_id)
        self.state = ReplayState(portfolio_id=self.portfolio_id)

    def process_event(self, event: OrderEventLog) -> None:
        """Apply a single domain event to the in-memory state."""
        etype = event.event_type
        payload = event.payload or {}

        if etype == "OrderCreated":
            if payload.get("portfolio_id") == self.portfolio_id:
                oid = payload["order_id"]
                l_price = Decimal(payload["limit_price"]) if payload.get("limit_price") else None
                self.state.orders[oid] = ReplayOrder(
                    order_id=oid,
                    instrument_id=payload["instrument_id"],
                    side=payload["side"],
                    order_type=payload["order_type"],
                    quantity=Decimal(payload["quantity"]),
                    limit_price=l_price,
                    status="created",
                )

        elif etype == "OrderValidated":
            oid = str(event.aggregate_id)
            if oid in self.state.orders:
                self.state.orders[oid].status = "validated"

        elif etype == "OrderAccepted":
            oid = str(event.aggregate_id)
            if oid in self.state.orders:
                self.state.orders[oid].status = "accepted"

        elif etype == "OrderPending":
            oid = str(event.aggregate_id)
            if oid in self.state.orders:
                self.state.orders[oid].status = "pending"

        elif etype in ("OrderFilled", "OrderPartiallyFilled"):
            oid = payload.get("order_id") or str(event.aggregate_id)
            if oid in self.state.orders:
                ord_obj = self.state.orders[oid]
                fill_qty = Decimal(payload["filled_quantity"])
                ord_obj.filled_quantity += fill_qty
                ord_obj.status = payload.get("status", "filled" if etype == "OrderFilled" else "partially_filled")

            if "fill_id" in payload:
                self.state.fills.append(
                    ReplayFill(
                        fill_id=payload["fill_id"],
                        order_id=oid,
                        quantity=Decimal(payload["filled_quantity"]),
                        price=Decimal(payload["fill_price"]),
                        total_charges=Decimal(payload.get("total_charges", "0.0000")),
                    )
                )

        elif etype == "OrderCancelled":
            oid = str(event.aggregate_id)
            if oid in self.state.orders:
                self.state.orders[oid].status = "cancelled"

        elif etype == "OrderRejected":
            oid = str(event.aggregate_id)
            if oid in self.state.orders:
                self.state.orders[oid].status = "rejected"
                self.state.orders[oid].rejected_reason = payload.get("reason")

        elif etype == "LedgerEntryCreated":
            if payload.get("portfolio_id") == self.portfolio_id:
                amount = Decimal(payload["amount"])
                self.state.cash_balance += amount

        elif etype == "CashReserved":
            if payload.get("portfolio_id") == self.portfolio_id:
                reserved = Decimal(payload["reserved_amount"])
                self.state.reserved_cash += reserved

        elif etype == "CashReleased":
            if payload.get("portfolio_id") == self.portfolio_id:
                released = Decimal(payload["released_amount"])
                self.state.reserved_cash -= released

        elif etype in ("PositionOpened", "PositionUpdated"):
            if payload.get("portfolio_id") == self.portfolio_id:
                inst_id = payload["instrument_id"]
                pos = self.state.positions.setdefault(inst_id, ReplayPosition(instrument_id=inst_id))
                pos.quantity = Decimal(payload["quantity"])
                pos.avg_entry_price = Decimal(payload["avg_entry_price"])
                if "realized_pnl" in payload:
                    pos.realized_pnl = Decimal(payload["realized_pnl"])
                pos.status = "open"

        elif etype == "PositionClosed":
            if payload.get("portfolio_id") == self.portfolio_id:
                inst_id = payload["instrument_id"]
                if inst_id in self.state.positions:
                    pos = self.state.positions[inst_id]
                    pos.quantity = Decimal("0.0000")
                    pos.avg_entry_price = Decimal("0.0000")
                    pos.realized_pnl = Decimal(payload["realized_pnl"])
                    pos.status = "closed"

        self.state.events_processed += 1

    def replay_all(self, events: list[OrderEventLog]) -> ReplayState:
        """Replay an entire list of chronological events."""
        for evt in events:
            self.process_event(evt)
        return self.state
