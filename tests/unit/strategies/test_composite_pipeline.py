"""Unit tests for Strategy Composition and Filter Pipelines."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
import pytest

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.strategies.base import StrategyContext
from app.domains.strategies.composite import ComposedStrategyPipeline
from app.domains.strategies.registry import StrategyRegistry
from app.domains.trading.clock import FixedClock
import app.domains.strategies.builtin


class TestCompositePipeline:
    """Validate strategy composition and filtering chaining."""

    def test_composite_pipeline_filtering(self):
        primary_strat = StrategyRegistry.create_instance(
            "rsi_momentum",
            params={"period": 5, "oversold_threshold": 30.0, "overbought_threshold": 70.0},
        )

        # Filter: Only allow signals if price is above 100.0
        def price_filter(bar: HistoricalBar, context: StrategyContext, signal) -> bool:
            return float(bar.close) > 100.0

        pipeline = ComposedStrategyPipeline(
            primary_strategy=primary_strat,
            filters=[price_filter],
        )

        instrument_id = uuid.uuid4()
        symbol = "FILTER_TEST"
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        clock = FixedClock(base_time)

        # Generate dip below oversold then recover below 100
        bars_below_100 = []
        for i in range(10):
            bar = HistoricalBar(
                instrument_id=instrument_id,
                symbol=symbol,
                timestamp=base_time + timedelta(minutes=i * 5),
                open=Decimal("95.00"),
                high=Decimal("96.00"),
                low=Decimal("90.00"),
                close=Decimal(str(90.0 + i * 0.5)),  # Closes < 100
                volume=1000,
            )
            bars_below_100.append(bar)

        pit_feed = PointInTimeDataFeed(clock=clock, bars=bars_below_100)
        portfolio_id = uuid.uuid4()

        filtered_signals = []
        for bar in bars_below_100:
            clock.set_time(bar.timestamp)
            ctx = StrategyContext(
                portfolio_id=portfolio_id,
                current_time=bar.timestamp,
                cash_balance=Decimal("100000.00"),
                current_equity=Decimal("100000.00"),
                positions={},
                data_feed=pit_feed,
            )
            filtered_signals.extend(pipeline.on_bar(bar, ctx))

        # Because price < 100, price_filter blocks all signals
        assert len(filtered_signals) == 0
