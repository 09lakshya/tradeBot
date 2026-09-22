"""Strategy Adapter and Signal Protocol for Backtesting."""
import abc
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.trading.enums import OrderSide, OrderType, ProductType


@dataclass(frozen=True)
class StrategySignal:
    """Explainable strategy trading signal with attribution metadata."""
    signal_id: uuid.UUID = field(default_factory=uuid.uuid4)
    strategy_id: str = "strategy"
    instrument_id: uuid.UUID = field(default_factory=uuid.uuid4)
    symbol: str = ""
    side: OrderSide = OrderSide.buy
    target_quantity: Decimal = Decimal("0.0000")
    order_type: OrderType = OrderType.market
    limit_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    product_type: ProductType = ProductType.cnc
    alpha_score: float = 1.0
    rule_reason: str = "Signal generated"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyContext:
    """Point-in-time restricted context provided to the strategy."""
    portfolio_id: uuid.UUID
    current_time: datetime
    cash_balance: Decimal
    current_equity: Decimal
    positions: dict[uuid.UUID, Decimal]  # instrument_id -> quantity
    data_feed: PointInTimeDataFeed

    def get_history(self, instrument_id: uuid.UUID, lookback_bars: int) -> list[HistoricalBar]:
        """Convenience method matching BaseStrategy interface."""
        return self.data_feed.get_history(instrument_id, lookback_bars=lookback_bars)

    def get_current_position(self, instrument_id: uuid.UUID) -> Decimal:
        """Convenience method matching BaseStrategy interface."""
        return self.positions.get(instrument_id, Decimal("0.0000"))


class BaseBacktestStrategy(abc.ABC):
    """Abstract base class for backtest strategies."""

    def __init__(self, params: dict[str, Any] | None = None):
        self.params = params or {}
        self.strategy_id = self.__class__.__name__

    def on_init(self, context: StrategyContext) -> None:
        """Called before historical replay begins."""
        pass

    @abc.abstractmethod
    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[StrategySignal]:
        """Evaluated sequentially on each bar event.
        Must return list of StrategySignals.
        """
        pass

    def on_fill(self, fill_data: dict[str, Any], context: StrategyContext) -> None:
        """Called when an order submitted by this strategy is filled."""
        pass

    def on_corporate_action(self, action_data: dict[str, Any], context: StrategyContext) -> None:
        """Called when a corporate action occurs on a held instrument."""
        pass


class BuyAndHoldStrategy(BaseBacktestStrategy):
    """Reference benchmark strategy: allocates 100% available cash on first bar."""

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        self._invested = False

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[StrategySignal]:
        if self._invested or context.cash_balance <= Decimal("100.0000"):
            return []

        # Allocate 95% of available cash balance to account for fees and buffer
        target_cash = context.cash_balance * Decimal("0.95")
        qty = (target_cash / bar.close).quantize(Decimal("1.0000"))
        if qty < Decimal("1.0000"):
            return []

        self._invested = True
        return [
            StrategySignal(
                strategy_id=self.strategy_id,
                instrument_id=bar.instrument_id,
                symbol=bar.symbol,
                side=OrderSide.buy,
                target_quantity=qty,
                order_type=OrderType.market,
                rule_reason="Initial Buy and Hold Allocation",
            )
        ]


class SMACrossoverStrategy(BaseBacktestStrategy):
    """Classic Simple Moving Average (SMA) crossover strategy."""

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        self.fast_period = int(self.params.get("fast_period", 10))
        self.slow_period = int(self.params.get("slow_period", 30))
        self.trade_qty = Decimal(str(self.params.get("trade_qty", "10.0000")))

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[StrategySignal]:
        history = context.data_feed.get_history(bar.instrument_id, lookback_bars=self.slow_period + 5)
        if len(history) < self.slow_period:
            return []

        closes = [float(b.close) for b in history]
        fast_sma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_sma = sum(closes[-self.slow_period:]) / self.slow_period

        prev_fast_sma = sum(closes[-self.fast_period - 1:-1]) / self.fast_period
        prev_slow_sma = sum(closes[-self.slow_period - 1:-1]) / self.slow_period

        current_pos = context.positions.get(bar.instrument_id, Decimal("0.0000"))
        signals = []

        # Bullish Crossover: fast crosses above slow
        if prev_fast_sma <= prev_slow_sma and fast_sma > slow_sma:
            if current_pos <= Decimal("0.0000"):
                signals.append(
                    StrategySignal(
                        strategy_id=self.strategy_id,
                        instrument_id=bar.instrument_id,
                        symbol=bar.symbol,
                        side=OrderSide.buy,
                        target_quantity=self.trade_qty,
                        order_type=OrderType.market,
                        rule_reason=f"Bullish SMA Crossover (Fast={fast_sma:.2f} > Slow={slow_sma:.2f})",
                        alpha_score=0.8,
                    )
                )

        # Bearish Crossover: fast crosses below slow
        elif prev_fast_sma >= prev_slow_sma and fast_sma < slow_sma:
            if current_pos > Decimal("0.0000"):
                signals.append(
                    StrategySignal(
                        strategy_id=self.strategy_id,
                        instrument_id=bar.instrument_id,
                        symbol=bar.symbol,
                        side=OrderSide.sell,
                        target_quantity=current_pos,
                        order_type=OrderType.market,
                        rule_reason=f"Bearish SMA Crossover (Fast={fast_sma:.2f} < Slow={slow_sma:.2f})",
                        alpha_score=-0.8,
                    )
                )

        return signals


class DomainStrategyBacktestAdapter(BaseBacktestStrategy):
    """Universal Adapter allowing any Phase 5 BaseStrategy to run in the Backtesting Engine."""

    def __init__(self, strategy_instance: Any):
        super().__init__(strategy_instance.params)
        self.strategy = strategy_instance
        self.strategy_id = strategy_instance.strategy_id

    def on_init(self, context: StrategyContext) -> None:
        self.strategy.initialize(context)

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[StrategySignal]:
        from app.domains.strategies.enums import SignalDirection, SignalType

        trading_signals = self.strategy.on_bar(bar, context)
        adapted_signals = []

        for ts in trading_signals:
            # These branches named SignalType members that do not exist
            # (rebalance_weight, stop_loss, take_profit), so this raised
            # AttributeError on the first signal it ever saw -- the adapter
            # could not run at all. Exits are checked first: an exit_long still
            # carries direction "long" and would otherwise be read as a buy.
            if ts.signal_type in (SignalType.exit_long, SignalType.exit_short):
                side = OrderSide.sell
            elif ts.signal_type == SignalType.hold:
                continue
            elif ts.direction == SignalDirection.long or ts.signal_type in (
                SignalType.entry_long,
                SignalType.rebalance,
            ):
                side = OrderSide.buy
            elif ts.direction in (SignalDirection.short, SignalDirection.flat):
                side = OrderSide.sell
            else:
                continue

            adapted_signals.append(
                StrategySignal(
                    signal_id=ts.signal_id,
                    strategy_id=ts.strategy_id,
                    instrument_id=ts.instrument_id,
                    symbol=ts.symbol,
                    side=side,
                    target_quantity=ts.target_quantity,
                    order_type=OrderType.market,
                    stop_loss=ts.stop_loss,
                    take_profit=ts.take_profit,
                    alpha_score=float(ts.confidence),
                    rule_reason=ts.human_readable_explanation,
                    metadata={
                        **ts.metadata,
                        "supporting_indicators": ts.supporting_indicators,
                        "market_regime": ts.market_regime.value,
                        "risk_reward_ratio": str(ts.risk_reward_ratio) if ts.risk_reward_ratio else None,
                    },
                )
            )

        return adapted_signals
