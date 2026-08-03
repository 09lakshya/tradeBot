"""Integration tests for end-to-end trading lifecycle pipeline."""
import uuid
from decimal import Decimal
import pytest

from app.domains.market_data.enums import AssetClass, Exchange
from app.domains.market_data.models import Instrument
from app.domains.trading.clock import FixedClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.enums import OrderSide, OrderStatus, OrderType, PositionStatus
from app.domains.trading.service import TradingService


def test_full_roundtrip_trading_lifecycle_pipeline(db):
    clock = FixedClock()
    cost_engine = CostEngine("zerodha")
    service = TradingService(db, clock, cost_engine=cost_engine)

    # 1. Setup Instrument
    inst = Instrument(
        trading_symbol="RELIANCE",
        name="Reliance Industries",
        exchange=Exchange.NSE,
        asset_class=AssetClass.equity,
    )
    db.add(inst)
    db.flush()

    # 2. Open Portfolio with 500,000 INR
    port = service.create_portfolio("Integration Master Port", Decimal("500000.0000"))
    assert port.cash_balance == Decimal("500000.0000")

    # 3. Buy 100 shares @ Limit 2400
    buy_order = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("100.0000"),
        limit_price=Decimal("2400.0000"),
    )
    assert buy_order.status == OrderStatus.pending
    assert port.reserved_cash > Decimal("0.0000")

    # 4. Fill Buy Order at Market 2390
    fill_buy = service.execute_order(buy_order.id, market_price=Decimal("2390.0000"))
    assert fill_buy is not None
    assert buy_order.status == OrderStatus.filled
    assert port.reserved_cash == Decimal("0.0000")

    # 5. Verify Position is Open
    pos = service.positions.get_position(port.id, inst.id)
    assert pos is not None
    assert pos.status == PositionStatus.open
    assert pos.quantity == Decimal("100.0000")
    assert pos.avg_entry_price == Decimal("2390.0000")

    # 6. Verify Cash Balance Decreased Accurately
    expected_debit = (Decimal("100.0000") * Decimal("2390.0000")) + fill_buy.total_charges
    assert port.cash_balance == (Decimal("500000.0000") - expected_debit)
    assert service.ledger.reconcile_balance(port.id) is True

    # 7. Sell 100 shares @ Market 2500 (Profit trade)
    sell_order = service.submit_order(
        portfolio_id=port.id,
        instrument_id=inst.id,
        side=OrderSide.sell,
        order_type=OrderType.market,
        quantity=Decimal("100.0000"),
    )
    fill_sell = service.execute_order(sell_order.id, market_price=Decimal("2500.0000"))
    assert fill_sell is not None
    assert sell_order.status == OrderStatus.filled

    # 8. Verify Position Closed & Realized P&L
    assert pos.status == PositionStatus.closed
    assert pos.quantity == Decimal("0.0000")
    # Gross profit = (fill_price - entry_price)*qty. Net profit = Gross profit - sell_charges
    expected_realized = (fill_sell.price - Decimal("2390.0000")) * Decimal("100.0000") - fill_sell.total_charges
    assert pos.realized_pnl == expected_realized.quantize(Decimal("0.0001"))

    # 9. Verify Ledger & Audit Stream
    assert service.ledger.reconcile_balance(port.id) is True
    audit_events = service.audit.get_events_for_aggregate(port.id)
    assert len(audit_events) >= 4  # deposit, reserved, released, buy_fill, sell_fill, etc.
