"""End-to-End Backtest Integration Tests using Phase 5 Strategies."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
import pytest
from sqlalchemy.orm import Session

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.backtest.driver import BacktestEngine
from app.domains.backtest.strategy_adapter import DomainStrategyBacktestAdapter
from app.domains.market_data.enums import Exchange
from app.domains.market_data.models import Instrument
from app.domains.risk.service import RiskService
from app.domains.strategies.registry import StrategyRegistry
from app.domains.trading.clock import ReplayClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.service import TradingService
import app.domains.strategies.builtin


@pytest.fixture
def strategy_test_instrument(db: Session) -> Instrument:
    inst = Instrument(
        trading_symbol="STRAT_TEST_STOCK",
        name="Strategy Test Stock Ltd",
        exchange=Exchange.NSE,
        tick_size=0.05,
        lot_size=1,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def generate_backtest_dataset(test_instrument: Instrument, num_bars: int = 150):
    """Generate synthetic trending price action."""
    start_time = datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc)
    base_price = Decimal("100.0000")
    bars = []

    for i in range(num_bars):
        t = start_time + timedelta(minutes=i * 5)
        price = base_price + Decimal(str(i * 0.5)) + (Decimal("2.0") if i % 2 == 0 else Decimal("-1.5"))
        bar = HistoricalBar(
            instrument_id=test_instrument.id,
            symbol=test_instrument.trading_symbol,
            timestamp=t,
            open=price - Decimal("0.20"),
            high=price + Decimal("0.80"),
            low=price - Decimal("0.80"),
            close=price,
            volume=20000,
        )
        bars.append(bar)

    return start_time, bars


class TestStrategyBacktestIntegration:
    """Validate that Phase 5 strategies integrate seamlessly with Phase 4 Backtesting Engine."""

    def test_ema_crossover_in_backtest_engine(self, db: Session, strategy_test_instrument: Instrument):
        start_time, bars = generate_backtest_dataset(strategy_test_instrument, num_bars=60)
        strat_instance = StrategyRegistry.create_instance(
            "ema_crossover",
            params={"fast_period": 5, "slow_period": 10, "trend_filter_period": 20, "trade_qty": "5.0000"},
        )
        adapted_strategy = DomainStrategyBacktestAdapter(strat_instance)

        clock = ReplayClock(start_time=start_time)
        feed = PointInTimeDataFeed(clock=clock, bars=bars)
        cost_engine = CostEngine("zerodha")
        risk_service = RiskService(clock=clock)
        trading_service = TradingService(db=db, clock=clock, cost_engine=cost_engine)

        portfolio = trading_service.create_portfolio("EMA Crossover Portfolio", initial_capital=Decimal("100000.0000"))

        engine = BacktestEngine(
            db=db,
            clock=clock,
            trading_service=trading_service,
            risk_service=risk_service,
            data_feed=feed,
            strategy=adapted_strategy,
        )
        result = engine.run(portfolio_id=portfolio.id)

        assert result is not None
        assert result.total_bars_processed == 60
        assert result.equity_curve is not None
        assert len(result.equity_curve) > 0

    def test_rsi_momentum_in_backtest_engine(self, db: Session, strategy_test_instrument: Instrument):
        start_time, bars = generate_backtest_dataset(strategy_test_instrument, num_bars=60)
        strat_instance = StrategyRegistry.create_instance(
            "rsi_momentum",
            params={"period": 10, "oversold_threshold": 30.0, "overbought_threshold": 70.0, "trade_qty": "5.0000"},
        )
        adapted_strategy = DomainStrategyBacktestAdapter(strat_instance)

        clock = ReplayClock(start_time=start_time)
        feed = PointInTimeDataFeed(clock=clock, bars=bars)
        cost_engine = CostEngine("zerodha")
        risk_service = RiskService(clock=clock)
        trading_service = TradingService(db=db, clock=clock, cost_engine=cost_engine)

        portfolio = trading_service.create_portfolio("RSI Momentum Portfolio", initial_capital=Decimal("100000.0000"))

        engine = BacktestEngine(
            db=db,
            clock=clock,
            trading_service=trading_service,
            risk_service=risk_service,
            data_feed=feed,
            strategy=adapted_strategy,
        )
        result = engine.run(portfolio_id=portfolio.id)

        assert result is not None
        assert result.total_bars_processed == 60
