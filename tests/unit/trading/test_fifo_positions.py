"""Unit tests for PositionManager and FIFO lot accounting."""
import uuid
from decimal import Decimal
import pytest

from app.domains.trading.clock import FixedClock
from app.domains.trading.enums import OrderSide, PositionStatus, ProductType
from app.domains.trading.exceptions import InsufficientPositionQuantityError
from app.domains.trading.models import Fill, Position, PositionLot
from app.domains.trading.positions import PositionManager


def _make_fill(
    portfolio_id: uuid.UUID,
    instrument_id: uuid.UUID,
    qty: Decimal,
    price: Decimal,
    total_charges: Decimal = Decimal("0.0000"),
) -> Fill:
    return Fill(
        order_id=uuid.uuid4(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        fill_sequence=1,
        quantity=qty,
        price=price,
        total_charges=total_charges,
    )


def test_fifo_single_buy_and_sell(db):
    clock = FixedClock()
    pm = PositionManager(db, clock)
    port_id = uuid.uuid4()
    inst_id = uuid.uuid4()

    # 1. Buy 100 @ 100
    fill1 = _make_fill(port_id, inst_id, Decimal("100.0000"), Decimal("100.0000"))
    db.add(fill1)
    db.flush()

    pos, evts = pm.apply_fill(fill1, OrderSide.buy)
    assert pos.quantity == Decimal("100.0000")
    assert pos.avg_entry_price == Decimal("100.0000")
    assert pos.status == PositionStatus.open
    assert len(evts) == 1
    assert evts[0].event_type == "PositionOpened"

    # 2. Sell 100 @ 120 (gain of 2000)
    fill2 = _make_fill(port_id, inst_id, Decimal("100.0000"), Decimal("120.0000"), total_charges=Decimal("10.0000"))
    db.add(fill2)
    db.flush()

    pos2, evts2 = pm.apply_fill(fill2, OrderSide.sell)
    assert pos2.quantity == Decimal("0.0000")
    assert pos2.status == PositionStatus.closed
    # Realized = (120 - 100)*100 - 10 = 2000 - 10 = 1990
    assert pos2.realized_pnl == Decimal("1990.0000")
    assert len(evts2) == 1
    assert evts2[0].event_type == "PositionClosed"


def test_fifo_multi_tranche_buy_and_partial_sell(db):
    clock = FixedClock()
    pm = PositionManager(db, clock)
    port_id = uuid.uuid4()
    inst_id = uuid.uuid4()

    # Tranche 1: Buy 50 @ 100
    fill1 = _make_fill(port_id, inst_id, Decimal("50.0000"), Decimal("100.0000"))
    db.add(fill1)
    db.flush()
    pm.apply_fill(fill1, OrderSide.buy)

    # Tranche 2: Buy 50 @ 200
    fill2 = _make_fill(port_id, inst_id, Decimal("50.0000"), Decimal("200.0000"))
    db.add(fill2)
    db.flush()
    pos, _ = pm.apply_fill(fill2, OrderSide.buy)

    # Total 100 shares, average price = (50*100 + 50*200)/100 = 150
    assert pos.quantity == Decimal("100.0000")
    assert pos.avg_entry_price == Decimal("150.0000")

    # Sell 70 @ 250 -> Consumes 50 from Lot 1 (@100) and 20 from Lot 2 (@200)
    # Lot 1 P&L = (250 - 100) * 50 = 7500
    # Lot 2 P&L = (250 - 200) * 20 = 1000
    # Total Gross Realized = 8500
    fill3 = _make_fill(port_id, inst_id, Decimal("70.0000"), Decimal("250.0000"))
    db.add(fill3)
    db.flush()

    pos3, _ = pm.apply_fill(fill3, OrderSide.sell)
    assert pos3.quantity == Decimal("30.0000")
    assert pos3.status == PositionStatus.open
    assert pos3.realized_pnl == Decimal("8500.0000")
    # Remaining 30 shares are exclusively from Lot 2 (@200)
    assert pos3.avg_entry_price == Decimal("200.0000")


def test_overselling_raises_exception(db):
    clock = FixedClock()
    pm = PositionManager(db, clock)
    port_id = uuid.uuid4()
    inst_id = uuid.uuid4()

    fill1 = _make_fill(port_id, inst_id, Decimal("20.0000"), Decimal("100.0000"))
    db.add(fill1)
    db.flush()
    pm.apply_fill(fill1, OrderSide.buy)

    fill_oversell = _make_fill(port_id, inst_id, Decimal("25.0000"), Decimal("110.0000"))
    db.add(fill_oversell)
    db.flush()

    with pytest.raises(InsufficientPositionQuantityError):
        pm.apply_fill(fill_oversell, OrderSide.sell)
