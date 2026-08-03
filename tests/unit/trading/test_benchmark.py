"""Performance benchmark for Paper Trading OMS throughput and state operations."""
import time
import uuid
from decimal import Decimal
import pytest

from app.domains.market_data.enums import AssetClass, Exchange
from app.domains.market_data.models import Instrument
from app.domains.trading.clock import FixedClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.enums import OrderSide, OrderType
from app.domains.trading.service import TradingService


def test_oms_execution_and_ledger_throughput(db):
    clock = FixedClock()
    cost_engine = CostEngine("zero_cost")
    service = TradingService(db, clock, cost_engine=cost_engine)

    inst = Instrument(
        trading_symbol="BENCHMARK_INST",
        name="Benchmark Stock",
        exchange=Exchange.NSE,
        asset_class=AssetClass.equity,
    )
    db.add(inst)
    db.flush()

    port = service.create_portfolio("Benchmark Port", Decimal("10000000.0000"))

    n_orders = 200
    start_time = time.perf_counter()

    for i in range(n_orders):
        order = service.submit_order(
            portfolio_id=port.id,
            instrument_id=inst.id,
            side=OrderSide.buy,
            order_type=OrderType.limit,
            quantity=Decimal("10.0000"),
            limit_price=Decimal("100.0000"),
        )
        service.execute_order(order.id, market_price=Decimal("100.0000"))

    duration = time.perf_counter() - start_time
    ops_per_second = (n_orders * 2) / duration

    # Reconcile after high-frequency batch
    reconciled = service.ledger.reconcile_balance(port.id)

    assert reconciled is True
    assert duration > 0
    print(f"\n[BENCHMARK] Processed {n_orders * 2} OMS operations in {duration:.4f}s ({ops_per_second:.1f} ops/sec)")
