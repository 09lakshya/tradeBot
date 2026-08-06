"""Integration tests for the complete Backtest pipeline."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy.orm import Session

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.backtest.driver import BacktestEngine
from app.domains.backtest.enums import BacktestStatus
from app.domains.backtest.schemas import BacktestCreateRequest, SlippageConfig
from app.domains.backtest.service import BacktestService
from app.domains.backtest.strategy_adapter import BuyAndHoldStrategy, SMACrossoverStrategy
from app.domains.market_data.enums import Exchange
from app.domains.market_data.models import Instrument
from app.domains.risk.service import RiskService
from app.domains.trading.clock import ReplayClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.service import TradingService


@pytest.fixture
def test_instrument(db: Session) -> Instrument:
    inst = Instrument(
        trading_symbol="RELIANCE",
        name="Reliance Industries Ltd",
        exchange=Exchange.NSE,
        tick_size=0.05,
        lot_size=1,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def test_backtest_engine_buy_and_hold(db: Session, test_instrument: Instrument):
    start_dt = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
    bars = []
    base_price = Decimal("2500.0000")
    for i in range(50):
        ts = start_dt + timedelta(days=i)
        p = base_price + Decimal(str(i * 10))
        bars.append(
            HistoricalBar(
                instrument_id=test_instrument.id,
                symbol=test_instrument.trading_symbol,
                timestamp=ts,
                open=p,
                high=p + Decimal("20.0"),
                low=p - Decimal("10.0"),
                close=p + Decimal("15.0"),
                volume=50000,
            )
        )

    clock = ReplayClock(start_time=start_dt)
    feed = PointInTimeDataFeed(clock=clock, bars=bars)
    cost_engine = CostEngine("zerodha")
    risk_service = RiskService(clock=clock)
    trading = TradingService(db=db, clock=clock, cost_engine=cost_engine, risk_service=risk_service)
    port = trading.create_portfolio("BT_Portfolio", initial_capital=Decimal("100000.0000"))

    strategy = BuyAndHoldStrategy()
    engine = BacktestEngine(
        db=db,
        clock=clock,
        trading_service=trading,
        risk_service=risk_service,
        data_feed=feed,
        strategy=strategy,
        random_seed=42,
    )

    result = engine.run(portfolio_id=port.id)

    assert result.total_bars_processed == 50
    assert len(result.trades) >= 1
    assert result.ending_capital > result.initial_capital
    assert result.total_return_pct > Decimal("0.0")
    assert len(result.equity_curve) == 50


def test_backtest_service_end_to_end(db: Session, test_instrument: Instrument):
    start_dt = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
    bars = []
    base_price = Decimal("2500.0000")
    for i in range(40):
        ts = start_dt + timedelta(days=i)
        p = base_price + Decimal(str(i * 5))
        bars.append(
            HistoricalBar(
                instrument_id=test_instrument.id,
                symbol=test_instrument.trading_symbol,
                timestamp=ts,
                open=p,
                high=p + Decimal("10.0"),
                low=p - Decimal("5.0"),
                close=p + Decimal("8.0"),
                volume=100000,
            )
        )

    clock = ReplayClock(start_time=start_dt)
    feed = PointInTimeDataFeed(clock=clock, bars=bars)

    service = BacktestService(db=db)
    req = BacktestCreateRequest(
        name="Integration Test Run",
        strategy_id="SMACrossoverStrategy",
        strategy_params={"fast_period": 5, "slow_period": 15, "trade_qty": "10.0000"},
        instrument_ids=[test_instrument.id],
        start_date=date(2025, 1, 1),
        end_date=date(2025, 2, 15),
        initial_capital=Decimal("100000.0000"),
        slippage=SlippageConfig(fixed_bps=Decimal("5.0000")),
    )

    bt = service.create_backtest(req)
    assert bt.status == BacktestStatus.queued

    completed_bt = service.run_backtest(bt.id, data_feed=feed)
    assert completed_bt.status == BacktestStatus.completed
    assert len(completed_bt.results) == 1

    primary_res = completed_bt.results[0]
    assert primary_res.metrics["total_return_pct"] is not None
    assert primary_res.metrics["sharpe_ratio"] is not None
