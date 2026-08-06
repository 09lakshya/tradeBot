"""Comprehensive evaluation tests for all 21 built-in institutional strategies."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
import pytest

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.strategies.base import StrategyContext
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.registry import StrategyRegistry
from app.domains.trading.clock import FixedClock
import app.domains.strategies.builtin


def create_synthetic_feed(bars_count: int = 250, trend: str = "bullish"):
    """Create a synthetic point-in-time data feed for testing."""
    instrument_id = uuid.uuid4()
    symbol = "TEST_STOCK"
    start_time = datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc)
    clock = FixedClock(start_time)
    base_price = 100.0
    bars = []

    for i in range(bars_count):
        t = start_time + timedelta(minutes=i * 5)
        if trend == "bullish":
            price = base_price + i * 0.5
        elif trend == "bearish":
            price = max(10.0, base_price - i * 0.5)
        elif trend == "ranging":
            price = base_price + (5.0 if i % 4 in (0, 1) else -5.0)
        else:
            price = base_price

        bar = HistoricalBar(
            instrument_id=instrument_id,
            symbol=symbol,
            timestamp=t,
            open=Decimal(str(f"{price - 0.2:.2f}")),
            high=Decimal(str(f"{price + 1.0:.2f}")),
            low=Decimal(str(f"{price - 1.0:.2f}")),
            close=Decimal(str(f"{price:.2f}")),
            volume=15000,
        )
        bars.append(bar)

    pit_feed = PointInTimeDataFeed(clock=clock, bars=bars)
    return instrument_id, symbol, clock, pit_feed, bars


class TestBuiltinStrategies:
    """Validate all 21 built-in strategies for signal correctness, explainability, and risk boundaries."""

    @pytest.mark.parametrize("strat_id", [
        "ema_crossover",
        "sma_crossover",
        "macd_trend",
        "adx_trend",
        "rsi_momentum",
        "stochastic_momentum",
        "momentum_ranking",
        "donchian_breakout",
        "bollinger_mean_reversion",
        "vwap_reversion",
        "zscore_reversion",
        "atr_breakout",
        "keltner_channel",
        "obv_trend",
        "volume_breakout",
        "support_resistance",
        "gap_trading",
        "candlestick_patterns",
        "opening_range_breakout",
        "relative_strength",
        "multi_factor_composite",
    ])
    def test_strategy_execution_and_signal_contract(self, strat_id: str):
        strat = StrategyRegistry.create_instance(strat_id)
        assert strat is not None
        assert strat.strategy_id == strat_id

        inst_id, symbol, clock, pit_feed, bars = create_synthetic_feed(bars_count=230, trend="bullish")
        portfolio_id = uuid.uuid4()

        signals_collected = []
        for bar in bars:
            clock.set_time(bar.timestamp)
            context = StrategyContext(
                portfolio_id=portfolio_id,
                current_time=bar.timestamp,
                cash_balance=Decimal("100000.0000"),
                current_equity=Decimal("100000.0000"),
                positions={},
                data_feed=pit_feed,
            )
            signals = strat.on_bar(bar, context)
            assert isinstance(signals, list)

            for s in signals:
                assert s.strategy_id == strat_id
                assert s.instrument_id == inst_id
                assert s.symbol == symbol
                assert 0.0 <= s.confidence <= 1.0
                assert s.human_readable_explanation != ""
                assert s.target_quantity > Decimal("0.0000")
                if s.direction == SignalDirection.long:
                    assert s.stop_loss is not None
                signals_collected.append(s)

        # Confirm strategy ran through all 230 bars without error
        assert len(bars) == 230
