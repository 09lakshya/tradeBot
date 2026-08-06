"""Strategy Purity & Deterministic Parity Tests."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
import pytest

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.strategies.base import StrategyContext
from app.domains.strategies.registry import StrategyRegistry
from app.domains.trading.clock import FixedClock
import app.domains.strategies.builtin


class TestStrategyPurity:
    """Validate strategy purity and deterministic signal reproducibility."""

    def test_deterministic_signal_parity(self):
        strat1 = StrategyRegistry.create_instance("ema_crossover", params={"fast_period": 5, "slow_period": 10, "trend_filter_period": 20})
        strat2 = StrategyRegistry.create_instance("ema_crossover", params={"fast_period": 5, "slow_period": 10, "trend_filter_period": 20})

        instrument_id = uuid.uuid4()
        symbol = "DETERMINISM_TEST"
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        bars = []

        for i in range(50):
            bar = HistoricalBar(
                instrument_id=instrument_id,
                symbol=symbol,
                timestamp=base_time + timedelta(minutes=i * 5),
                open=Decimal(str(100.0 + i * 0.8)),
                high=Decimal(str(101.0 + i * 0.8)),
                low=Decimal(str(99.0 + i * 0.8)),
                close=Decimal(str(100.5 + i * 0.8)),
                volume=1000,
            )
            bars.append(bar)

        clock1 = FixedClock(base_time)
        pit_feed1 = PointInTimeDataFeed(clock=clock1, bars=bars)
        clock2 = FixedClock(base_time)
        pit_feed2 = PointInTimeDataFeed(clock=clock2, bars=bars)

        portfolio_id = uuid.uuid4()
        signals_run1 = []
        signals_run2 = []

        # Run 1
        for bar in bars:
            clock1.set_time(bar.timestamp)
            ctx1 = StrategyContext(
                portfolio_id=portfolio_id,
                current_time=bar.timestamp,
                cash_balance=Decimal("100000.00"),
                current_equity=Decimal("100000.00"),
                positions={},
                data_feed=pit_feed1,
            )
            signals_run1.extend(strat1.on_bar(bar, ctx1))

        # Run 2
        for bar in bars:
            clock2.set_time(bar.timestamp)
            ctx2 = StrategyContext(
                portfolio_id=portfolio_id,
                current_time=bar.timestamp,
                cash_balance=Decimal("100000.00"),
                current_equity=Decimal("100000.00"),
                positions={},
                data_feed=pit_feed2,
            )
            signals_run2.extend(strat2.on_bar(bar, ctx2))

        assert len(signals_run1) == len(signals_run2)
        for s1, s2 in zip(signals_run1, signals_run2):
            assert s1.strategy_id == s2.strategy_id
            assert s1.signal_type == s2.signal_type
            assert s1.direction == s2.direction
            assert s1.target_quantity == s2.target_quantity
            assert s1.entry_price == s2.entry_price
            assert s1.stop_loss == s2.stop_loss
            assert s1.take_profit == s2.take_profit
            assert s1.confidence == s2.confidence
            assert s1.market_regime == s2.market_regime
            assert s1.human_readable_explanation == s2.human_readable_explanation
