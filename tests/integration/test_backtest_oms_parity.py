"""Critical Parity Tests: Backtest Engine vs Paper OMS.
Proves ADR-0012: The Backtest Engine reuses the exact same OMS, Risk, Cost,
FIFO Position Manager, and Double-Entry Ledger without any simulator drift.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy.orm import Session

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.backtest.driver import BacktestEngine
from app.domains.backtest.slippage import FixedBpsSlippage
from app.domains.backtest.strategy_adapter import BaseBacktestStrategy, StrategyContext, StrategySignal
from app.domains.market_data.enums import Exchange
from app.domains.market_data.models import Instrument
from app.domains.risk.service import RiskService
from app.domains.trading.clock import ReplayClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.enums import OrderSide, OrderType, ProductType
from app.domains.trading.service import TradingService


class FixedScriptedStrategy(BaseBacktestStrategy):
    """Strategy that executes deterministic predefined actions on specific bar indices."""

    def __init__(self, actions: dict[int, tuple[OrderSide, Decimal]]):
        super().__init__()
        self.actions = actions  # bar_idx -> (side, qty)
        self.bar_count = 0

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[StrategySignal]:
        signals = []
        if self.bar_count in self.actions:
            side, qty = self.actions[self.bar_count]
            signals.append(
                StrategySignal(
                    strategy_id=self.strategy_id,
                    instrument_id=bar.instrument_id,
                    symbol=bar.symbol,
                    side=side,
                    target_quantity=qty,
                    order_type=OrderType.market,
                    rule_reason=f"Scripted action on bar {self.bar_count}",
                )
            )
        self.bar_count += 1
        return signals


def test_backtest_paper_oms_exact_financial_parity(db: Session):
    """Verifies that running orders through the Backtest Engine results in the exact same
    accounting balances, positions, fees, and ledger entries as direct OMS execution.
    """
    inst = Instrument(
        trading_symbol="INFY",
        name="Infosys Ltd",
        exchange=Exchange.NSE,
        tick_size=0.05,
        lot_size=1,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)

    start_dt = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
    
    bars = [
        HistoricalBar(inst.id, "INFY", start_dt, Decimal("1480.0"), Decimal("1500.0"), Decimal("1470.0"), Decimal("1490.0"), 50000),
        HistoricalBar(inst.id, "INFY", start_dt + timedelta(days=1), Decimal("1500.0"), Decimal("1520.0"), Decimal("1495.0"), Decimal("1510.0"), 60000),
        HistoricalBar(inst.id, "INFY", start_dt + timedelta(days=2), Decimal("1550.0"), Decimal("1570.0"), Decimal("1540.0"), Decimal("1560.0"), 70000),
        HistoricalBar(inst.id, "INFY", start_dt + timedelta(days=3), Decimal("1580.0"), Decimal("1610.0"), Decimal("1575.0"), Decimal("1600.0"), 80000),
    ]

    # --- 1. RUN THROUGH BACKTEST ENGINE (Zero Slippage for direct price parity) ---
    bt_clock = ReplayClock(start_time=start_dt)
    bt_feed = PointInTimeDataFeed(clock=bt_clock, bars=bars)
    bt_cost = CostEngine("zerodha")
    bt_risk = RiskService(clock=bt_clock)
    bt_trading = TradingService(db=db, clock=bt_clock, cost_engine=bt_cost, risk_service=bt_risk)
    bt_port = bt_trading.create_portfolio("BT_Parity_Port", initial_capital=Decimal("100000.0000"))

    strategy = FixedScriptedStrategy(
        actions={
            0: (OrderSide.buy, Decimal("10.0000")),
            1: (OrderSide.sell, Decimal("5.0000")),
        }
    )

    bt_engine = BacktestEngine(
        db=db,
        clock=bt_clock,
        trading_service=bt_trading,
        risk_service=bt_risk,
        data_feed=bt_feed,
        strategy=strategy,
        slippage_model=FixedBpsSlippage(fixed_bps=Decimal("0.0")),
        random_seed=42,
    )

    bt_result = bt_engine.run(portfolio_id=bt_port.id)

    # --- 2. RUN DIRECTLY THROUGH PAPER OMS ---
    direct_clock = ReplayClock(start_time=start_dt)
    direct_cost = CostEngine("zerodha")
    direct_risk = RiskService(clock=direct_clock)
    direct_trading = TradingService(db=db, clock=direct_clock, cost_engine=direct_cost, risk_service=direct_risk)
    direct_port = direct_trading.create_portfolio("Direct_OMS_Port", initial_capital=Decimal("100000.0000"))

    # Day 0 close -> submit buy 10
    direct_clock.step_to(start_dt)
    o1 = direct_trading.submit_order(
        portfolio_id=direct_port.id,
        instrument_id=inst.id,
        side=OrderSide.buy,
        order_type=OrderType.market,
        quantity=Decimal("10.0000"),
        product_type=ProductType.cnc,
    )
    # Day 1 open @ 1500.0 -> execute o1
    direct_clock.step_to(start_dt + timedelta(days=1))
    f1 = direct_trading.execute_order(order_id=o1.id, market_price=Decimal("1500.0000"))

    # Day 1 close -> submit sell 5
    o2 = direct_trading.submit_order(
        portfolio_id=direct_port.id,
        instrument_id=inst.id,
        side=OrderSide.sell,
        order_type=OrderType.market,
        quantity=Decimal("5.0000"),
        product_type=ProductType.cnc,
    )
    # Day 2 open @ 1550.0 -> execute o2
    direct_clock.step_to(start_dt + timedelta(days=2))
    f2 = direct_trading.execute_order(order_id=o2.id, market_price=Decimal("1550.0000"))

    # Day 3 close @ 1600.0 -> update position MTM
    direct_clock.step_to(start_dt + timedelta(days=3))
    direct_pos = direct_trading.positions.get_position(direct_port.id, inst.id)
    direct_pos.current_price = Decimal("1600.0000")
    direct_pos.unrealized_pnl = ((Decimal("1600.0000") - direct_pos.avg_entry_price) * direct_pos.quantity).quantize(Decimal("0.0001"))
    db.flush()

    # --- 3. ASSERT EXACT DECIMAL PARITY ---
    bt_summary = bt_trading.get_portfolio_summary(bt_port.id)
    direct_summary = direct_trading.get_portfolio_summary(direct_port.id)

    assert bt_summary.cash_balance == direct_summary.cash_balance
    assert bt_summary.open_positions_market_value == direct_summary.open_positions_market_value
    assert bt_summary.portfolio_total_value == direct_summary.portfolio_total_value
    assert bt_summary.total_realized_pnl == direct_summary.total_realized_pnl
    assert bt_summary.total_unrealized_pnl == direct_summary.total_unrealized_pnl

    bt_position = bt_trading.positions.get_position(bt_port.id, inst.id)
    assert bt_position.quantity == direct_pos.quantity
    assert bt_position.avg_entry_price == direct_pos.avg_entry_price

    bt_ledger = bt_trading.ledger.get_portfolio_entries(bt_port.id)
    direct_ledger = direct_trading.ledger.get_portfolio_entries(direct_port.id)
    assert len(bt_ledger) == len(direct_ledger)
    for b_e, d_e in zip(bt_ledger, direct_ledger):
        assert b_e.amount == d_e.amount
        assert b_e.txn_type == d_e.txn_type
