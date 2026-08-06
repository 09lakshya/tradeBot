"""Point-in-Time safety tests: ensuring strategies cannot access future data or introduce look-ahead bias."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
import pytest

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.strategies.base import StrategyContext
from app.domains.strategies.exceptions import StrategyLookAheadBiasError
from app.domains.trading.clock import FixedClock


class TestPointInTimeSafety:
    """Point-in-Time invariant validation."""

    def test_context_prevents_look_ahead_bias(self):
        instrument_id = uuid.uuid4()
        symbol = "PIT_TEST"
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        clock = FixedClock(base_time)
        bars = []

        for i in range(10):
            bars.append(
                HistoricalBar(
                    instrument_id=instrument_id,
                    symbol=symbol,
                    timestamp=base_time + timedelta(minutes=i * 5),
                    open=Decimal("100.00"),
                    high=Decimal("101.00"),
                    low=Decimal("99.00"),
                    close=Decimal("100.50"),
                    volume=1000,
                )
            )

        pit_feed = PointInTimeDataFeed(clock=clock, bars=bars)
        current_time = base_time + timedelta(minutes=3 * 5)  # Bar index 3
        clock.set_time(current_time)

        context = StrategyContext(
            portfolio_id=uuid.uuid4(),
            current_time=current_time,
            cash_balance=Decimal("50000.00"),
            current_equity=Decimal("50000.00"),
            positions={},
            data_feed=pit_feed,
        )

        # Lookback up to current_time is allowed
        history = context.get_history(instrument_id, lookback_bars=10)
        assert len(history) == 4  # Bars 0, 1, 2, 3
        assert all(b.timestamp <= current_time for b in history)

    def test_context_raises_if_future_bar_injected(self):
        instrument_id = uuid.uuid4()
        symbol = "PIT_TEST"
        current_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        future_time = current_time + timedelta(minutes=30)
        clock = FixedClock(current_time)

        # Manually create mock data feed that returns future bar
        class LeakyDataFeed(PointInTimeDataFeed):
            def get_history(self, inst_id, lookback_bars=10):
                return [
                    HistoricalBar(
                        instrument_id=inst_id,
                        symbol=symbol,
                        timestamp=future_time,
                        open=Decimal("100.00"),
                        high=Decimal("101.00"),
                        low=Decimal("99.00"),
                        close=Decimal("100.50"),
                        volume=1000,
                    )
                ]

        leaky_feed = LeakyDataFeed(clock=clock)
        context = StrategyContext(
            portfolio_id=uuid.uuid4(),
            current_time=current_time,
            cash_balance=Decimal("50000.00"),
            current_equity=Decimal("50000.00"),
            positions={},
            data_feed=leaky_feed,
        )

        with pytest.raises(StrategyLookAheadBiasError):
            context.get_history(instrument_id, lookback_bars=5)
