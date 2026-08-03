"""Unit tests for ExecutionSimulator."""
import uuid
from decimal import Decimal
import pytest

from app.domains.market_data.enums import Exchange
from app.domains.trading.clock import FixedClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.enums import OrderSide, OrderStatus, OrderType, ProductType
from app.domains.trading.models import Order
from app.domains.trading.simulator import ExecutionSimulator


def _make_order(side: OrderSide, otype: OrderType, qty: Decimal, limit_price: Decimal | None = None, stop_price: Decimal | None = None) -> Order:
    return Order(
        portfolio_id=uuid.uuid4(),
        instrument_id=uuid.uuid4(),
        side=side,
        order_type=otype,
        quantity=qty,
        filled_quantity=Decimal("0.0000"),
        limit_price=limit_price,
        stop_price=stop_price,
        status=OrderStatus.pending,
    )


def test_market_order_slippage():
    clock = FixedClock()
    engine = CostEngine("zerodha")
    sim = ExecutionSimulator(cost_engine=engine, clock=clock, slippage_bps=Decimal("10.0"))  # 10 bps = 0.1%

    # BUY Market at 1000 -> Exec price = 1000 * 1.001 = 1001.00
    buy_order = _make_order(OrderSide.buy, OrderType.market, Decimal("100.0000"))
    res = sim.evaluate_execution(buy_order, market_price=Decimal("1000.0000"))
    assert res is not None
    assert res.price == Decimal("1001.0000")
    assert res.slippage == Decimal("1.0000")
    assert res.quantity == Decimal("100.0000")

    # SELL Market at 1000 -> Exec price = 1000 * 0.999 = 999.00
    sell_order = _make_order(OrderSide.sell, OrderType.market, Decimal("100.0000"))
    res_sell = sim.evaluate_execution(sell_order, market_price=Decimal("1000.0000"))
    assert res_sell is not None
    assert res_sell.price == Decimal("999.0000")


def test_limit_order_execution_rules():
    clock = FixedClock()
    engine = CostEngine("zero_cost")
    sim = ExecutionSimulator(cost_engine=engine, clock=clock)

    # Buy Limit @ 100
    buy_lim = _make_order(OrderSide.buy, OrderType.limit, Decimal("50.0000"), limit_price=Decimal("100.0000"))

    # Market is 105 -> Should NOT fill
    assert sim.evaluate_execution(buy_lim, market_price=Decimal("105.0000")) is None

    # Market is 98 -> Fills at 98 (price improvement)
    res = sim.evaluate_execution(buy_lim, market_price=Decimal("98.0000"))
    assert res is not None
    assert res.price == Decimal("98.0000")

    # Sell Limit @ 100
    sell_lim = _make_order(OrderSide.sell, OrderType.limit, Decimal("50.0000"), limit_price=Decimal("100.0000"))

    # Market is 95 -> Should NOT fill
    assert sim.evaluate_execution(sell_lim, market_price=Decimal("95.0000")) is None

    # Market is 102 -> Fills at 102
    res_sell = sim.evaluate_execution(sell_lim, market_price=Decimal("102.0000"))
    assert res_sell is not None
    assert res_sell.price == Decimal("102.0000")
