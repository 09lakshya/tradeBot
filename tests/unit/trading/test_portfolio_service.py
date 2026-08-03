"""Unit tests for Portfolio financial metrics and valuation."""
import uuid
from decimal import Decimal
import pytest

from app.domains.market_data.enums import AssetClass, Exchange
from app.domains.market_data.models import Instrument
from app.domains.trading.clock import FixedClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.enums import OrderSide, OrderType
from app.domains.trading.service import TradingService


def test_portfolio_summary_and_net_liquidation_value(db):
    clock = FixedClock()
    cost_engine = CostEngine("zero_cost")
    service = TradingService(db, clock, cost_engine=cost_engine)

    inst = Instrument(
        trading_symbol="INFY",
        name="Infosys Ltd",
        exchange=Exchange.NSE,
        asset_class=AssetClass.equity,
    )
    db.add(inst)
    db.flush()

    port = service.create_portfolio("Valuation Port", Decimal("200000.0000"))

    # Buy 100 shares @ 1500 = 150,000
    order = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("100.0000"),
        limit_price=Decimal("1500.0000"),
    )
    service.execute_order(order.id, market_price=Decimal("1500.0000"))

    # Initial mark to market summary (stock price = 1500)
    summary1 = service.get_portfolio_summary(port.id)
    assert summary1.cash_balance == Decimal("50000.0000")
    assert summary1.invested_capital == Decimal("150000.0000")
    assert summary1.open_positions_market_value == Decimal("150000.0000")
    assert summary1.portfolio_total_value == Decimal("200000.0000")
    assert summary1.total_unrealized_pnl == Decimal("0.0000")

    # Stock price appreciates to 1600 (gain of 10,000)
    summary2 = service.get_portfolio_summary(port.id, current_prices={inst.id: Decimal("1600.0000")})
    assert summary2.open_positions_market_value == Decimal("160000.0000")
    assert summary2.portfolio_total_value == Decimal("210000.0000")
    assert summary2.total_unrealized_pnl == Decimal("10000.0000")
