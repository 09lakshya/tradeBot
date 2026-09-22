"""The adapter that lets a domain strategy run inside the backtest engine.

It referenced three SignalType members that do not exist (``rebalance_weight``,
``stop_loss``, ``take_profit``), so it raised AttributeError on the first signal
it ever received. Nothing caught that because the backtest service never used the
adapter: every strategy id except ``sma_crossover`` silently fell through to
BuyAndHold, which meant "backtesting" any other strategy measured buy-and-hold
and reported it under that strategy's name.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.domains.backtest.strategy_adapter import DomainStrategyBacktestAdapter
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.enums import OrderSide

INSTRUMENT_ID = uuid.uuid4()


def _signal(signal_type: SignalType, direction: SignalDirection) -> TradingSignal:
    return TradingSignal(
        strategy_id="unit_test_strategy",
        instrument_id=INSTRUMENT_ID,
        symbol="TESTCO",
        timestamp=datetime.now(UTC),
        signal_type=signal_type,
        direction=direction,
        confidence=0.9,
        target_quantity=Decimal("10"),
        entry_price=Decimal("100"),
    )


class _StubStrategy:
    """Minimal stand-in for a registered domain strategy."""

    strategy_id = "unit_test_strategy"
    params: dict = {}

    def __init__(self, signals: list[TradingSignal]) -> None:
        self._signals = signals

    def initialize(self, context) -> None:  # noqa: ANN001
        return None

    def on_bar(self, bar, context) -> list[TradingSignal]:  # noqa: ANN001
        return self._signals


@pytest.mark.parametrize(
    ("signal_type", "direction", "expected_side"),
    [
        (SignalType.entry_long, SignalDirection.long, OrderSide.buy),
        (SignalType.rebalance, SignalDirection.long, OrderSide.buy),
        # An exit still carries direction "long"; read as a buy it would double
        # the position it was meant to close.
        (SignalType.exit_long, SignalDirection.long, OrderSide.sell),
        (SignalType.exit_short, SignalDirection.short, OrderSide.sell),
        (SignalType.entry_short, SignalDirection.short, OrderSide.sell),
    ],
)
def test_signal_types_map_to_the_right_side(
    signal_type: SignalType, direction: SignalDirection, expected_side: OrderSide
) -> None:
    adapter = DomainStrategyBacktestAdapter(_StubStrategy([_signal(signal_type, direction)]))
    produced = adapter.on_bar(bar=None, context=None)
    assert len(produced) == 1, f"{signal_type} produced no order"
    assert produced[0].side == expected_side


def test_hold_signals_produce_no_order() -> None:
    adapter = DomainStrategyBacktestAdapter(
        _StubStrategy([_signal(SignalType.hold, SignalDirection.flat)])
    )
    assert adapter.on_bar(bar=None, context=None) == []


def test_every_signal_type_is_handled_without_raising() -> None:
    """The original failure mode: an unknown attribute blew up the whole run."""
    for signal_type in SignalType:
        for direction in SignalDirection:
            adapter = DomainStrategyBacktestAdapter(
                _StubStrategy([_signal(signal_type, direction)])
            )
            adapter.on_bar(bar=None, context=None)  # must not raise
