"""Unit tests for TradingService order submission, execution, and cancellation."""
import uuid
from decimal import Decimal
import pytest

from app.domains.market_data.enums import AssetClass, Exchange
from app.domains.market_data.models import Instrument
from app.domains.trading.clock import FixedClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.enums import OrderSide, OrderStatus, OrderType, ProductType
from app.domains.trading.exceptions import (
    DuplicateIdempotencyKeyError,
    InsufficientBuyingPowerError,
    OrderNotCancellableError,
)
from app.domains.trading.service import TradingService


def _setup_instrument(db) -> Instrument:
    inst = Instrument(
        trading_symbol="TCS",
        name="Tata Consultancy Services",
        exchange=Exchange.NSE,
        asset_class=AssetClass.equity,
    )
    db.add(inst)
    db.flush()
    return inst


def test_order_submission_and_fill_lifecycle(db):
    clock = FixedClock()
    cost_engine = CostEngine("zero_cost")
    service = TradingService(db, clock, cost_engine=cost_engine)
    inst = _setup_instrument(db)

    # 1. Create Portfolio with 100,000 INR
    port = service.create_portfolio("Main OMS Portfolio", Decimal("100000.0000"))

    # 2. Submit Buy Limit Order (100 shares @ 500 = 50,000)
    order = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("100.0000"),
        limit_price=Decimal("500.0000"),
        decision={
            "entry_reason": "Mean reversion dip",
            "summary": "Bought TCS dip with 85% model confidence",
            "model_confidence": 0.85,
        },
    )
    assert order.status == OrderStatus.pending
    assert order.decision is not None
    assert order.decision.entry_reason == "Mean reversion dip"
    # Cash reserved
    assert port.reserved_cash > Decimal("0.0000")

    # 3. Execute Order at market price 495 (favorable limit execution)
    fill = service.execute_order(order.id, market_price=Decimal("495.0000"))
    assert fill is not None
    assert fill.quantity == Decimal("100.0000")
    assert fill.price == Decimal("495.0000")
    assert order.status == OrderStatus.filled
    assert order.filled_quantity == Decimal("100.0000")
    assert order.avg_fill_price == Decimal("495.0000")

    # Reserved cash released and cash debited (100,000 - 49,500 = 50,500)
    assert port.reserved_cash == Decimal("0.0000")
    assert port.cash_balance == Decimal("50500.0000")

    # Check Position
    pos = service.positions.get_position(port.id, inst.id)
    assert pos is not None
    assert pos.quantity == Decimal("100.0000")
    assert pos.avg_entry_price == Decimal("495.0000")


def test_idempotency_key_enforcement(db):
    clock = FixedClock()
    service = TradingService(db, clock)
    inst = _setup_instrument(db)
    port = service.create_portfolio("Idemp Port", Decimal("50000.0000"))

    idemp_key = "trade-signal-12345"
    service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("10.0000"),
        limit_price=Decimal("100.0000"),
        idempotency_key=idemp_key,
    )

    with pytest.raises(DuplicateIdempotencyKeyError):
        service.submit_order(
            portfolio_id=port.id,
            instrument_id=inst.id,
            side=OrderSide.buy,
            order_type=OrderType.limit,
            quantity=Decimal("10.0000"),
            limit_price=Decimal("100.0000"),
            idempotency_key=idemp_key,
        )


def test_order_cancellation_and_cash_release(db):
    clock = FixedClock()
    service = TradingService(db, clock)
    inst = _setup_instrument(db)
    port = service.create_portfolio("Cancel Port", Decimal("50000.0000"))

    order = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("20.0000"),
        limit_price=Decimal("1000.0000"),
    )
    assert port.reserved_cash > Decimal("0.0000")

    # Cancel order
    cancelled_order = service.cancel_order(order.id, reason="Changed strategy")
    assert cancelled_order.status == OrderStatus.cancelled
    assert cancelled_order.rejected_reason == "Changed strategy"
    assert port.reserved_cash == Decimal("0.0000")

    # Re-cancelling raises error
    with pytest.raises(OrderNotCancellableError):
        service.cancel_order(order.id)


def test_concurrent_multi_order_buying_power_isolation(db):
    """Ensure that filling or cancelling Order A does not release Order B's reserved cash."""
    clock = FixedClock()
    cost_engine = CostEngine("zero_cost")
    service = TradingService(db, clock, cost_engine=cost_engine)
    inst = _setup_instrument(db)
    port = service.create_portfolio("Multi Order Port", Decimal("100000.0000"))

    # Submit Order A (reserve 20,000)
    order_a = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("20.0000"),
        limit_price=Decimal("1000.0000"),
    )
    # Submit Order B (reserve 30,000)
    order_b = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("30.0000"),
        limit_price=Decimal("1000.0000"),
    )

    assert port.reserved_cash == Decimal("50000.0000")
    assert order_a.reserved_cash == Decimal("20000.0000")
    assert order_b.reserved_cash == Decimal("30000.0000")

    # Execute Order A completely
    service.execute_order(order_a.id, market_price=Decimal("1000.0000"))

    # Order B's reservation must still remain intact!
    assert port.reserved_cash == Decimal("30000.0000")
    assert order_b.reserved_cash == Decimal("30000.0000")
    assert port.cash_balance == Decimal("80000.0000")  # 100,000 - 20,000 paid

    # Now cancel Order B
    service.cancel_order(order_b.id)
    assert port.reserved_cash == Decimal("0.0000")
    assert port.cash_balance == Decimal("80000.0000")


def test_partial_fill_proportional_cash_release(db):
    """Ensure partial fills release proportional reserved cash."""
    clock = FixedClock()
    cost_engine = CostEngine("zero_cost")
    service = TradingService(db, clock, cost_engine=cost_engine)
    inst = _setup_instrument(db)
    port = service.create_portfolio("Partial Port", Decimal("100000.0000"))

    # Submit Order for 100 units @ 500 = 50,000 reserved
    order = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("100.0000"),
        limit_price=Decimal("500.0000"),
    )
    assert port.reserved_cash == Decimal("50000.0000")

    # Execute partial fill of 40 units (40% of order)
    fill = service.execute_order(
        order.id,
        market_price=Decimal("500.0000"),
        fill_quantity=Decimal("40.0000"),
    )
    assert fill is not None
    assert order.status == OrderStatus.partial
    assert order.filled_quantity == Decimal("40.0000")
    # 40% (20,000) released from reservation, remaining 30,000 reserved
    assert port.reserved_cash == Decimal("30000.0000")
    assert port.cash_balance == Decimal("80000.0000")  # 100k - 20k paid

