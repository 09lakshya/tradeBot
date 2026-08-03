"""Unit tests for DeterministicReplayEngine."""
import uuid
from decimal import Decimal
import pytest

from app.domains.market_data.enums import AssetClass, Exchange
from app.domains.market_data.models import Instrument
from app.domains.trading.clock import FixedClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.enums import OrderSide, OrderType
from app.domains.trading.replay import DeterministicReplayEngine
from app.domains.trading.service import TradingService


def test_deterministic_replay_state_reconstruction(db):
    clock = FixedClock()
    cost_engine = CostEngine("zero_cost")
    service = TradingService(db, clock, cost_engine=cost_engine)

    inst = Instrument(
        trading_symbol="HDFCBANK",
        name="HDFC Bank Ltd",
        exchange=Exchange.NSE,
        asset_class=AssetClass.equity,
    )
    db.add(inst)
    db.flush()

    # 1. Create portfolio with 100,000
    port = service.create_portfolio("Replay Test Port", Decimal("100000.0000"))

    # 2. Buy 100 shares @ 1000 = 100,000
    order1 = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("100.0000"),
        limit_price=Decimal("1000.0000"),
    )
    service.execute_order(order1.id, market_price=Decimal("1000.0000"))

    # 3. Sell 50 shares @ 1200
    order2 = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.sell,
        order_type=OrderType.limit,
        quantity=Decimal("50.0000"),
        limit_price=Decimal("1200.0000"),
    )
    service.execute_order(order2.id, market_price=Decimal("1200.0000"))

    # Fetch all events from audit stream
    events = service.audit.get_events_for_aggregate(port.id)
    # Also collect position and order events
    pos = service.positions.get_position(port.id, inst.id)
    all_events = (
        service.audit.get_events_for_aggregate(port.id)
        + service.audit.get_events_for_aggregate(pos.id)
        + service.audit.get_events_for_aggregate(order1.id)
        + service.audit.get_events_for_aggregate(order2.id)
    )

    # Replay all events from scratch
    replay_engine = DeterministicReplayEngine(port.id)
    replayed_state = replay_engine.replay_all(all_events)

    # Replayed cash balance: 100,000 - 100,000 + 60,000 = 60,000
    assert replayed_state.cash_balance == port.cash_balance
    assert replayed_state.cash_balance == Decimal("60000.0000")

    # Replayed position: 50 shares
    replayed_pos = replayed_state.positions[str(inst.id)]
    assert replayed_pos.quantity == pos.quantity
    assert replayed_pos.quantity == Decimal("50.0000")
    assert replayed_pos.realized_pnl == pos.realized_pnl
    assert replayed_pos.realized_pnl == Decimal("10000.0000")

    # Replayed orders & fills
    assert str(order1.id) in replayed_state.orders
    assert str(order2.id) in replayed_state.orders
    assert replayed_state.orders[str(order1.id)].status == "filled"
    assert replayed_state.orders[str(order1.id)].filled_quantity == Decimal("100.0000")
    assert len(replayed_state.fills) == 2
