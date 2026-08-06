"""SMA Crossover Strategy (Golden Cross / Death Cross)."""
from decimal import Decimal
from typing import Any

from app.domains.backtest.data_feed import HistoricalBar
from app.domains.strategies.base import BaseStrategy, StrategyContext
from app.domains.strategies.enums import (
    MarketRegime,
    SignalDirection,
    SignalType,
    StrategyCategory,
)
from app.domains.strategies.indicators import sma
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class SMACrossoverStrategy(BaseStrategy):
    """Simple Moving Average Golden Cross (50 SMA x 200 SMA) and Death Cross."""

    strategy_id: str = "sma_crossover"
    strategy_name: str = "SMA Golden Cross Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Executes on classic SMA golden cross with customizable fast and slow periods."
    category: StrategyCategory = StrategyCategory.trend_following
    required_lookback: int = 210

    default_parameters: dict[str, Any] = {
        "fast_period": 50,
        "slow_period": 200,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0300",
        "take_profit_pct": "0.0800",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        slow_p = int(self.params["slow_period"])
        history = context.get_history(bar.instrument_id, lookback_bars=slow_p + 10)
        if len(history) < slow_p:
            return []

        closes = [float(b.close) for b in history]
        fast_p = int(self.params["fast_period"])

        fast_sma = sma(closes, fast_p)
        slow_sma = sma(closes, slow_p)

        curr_fast, prev_fast = fast_sma[-1], fast_sma[-2]
        curr_slow, prev_slow = slow_sma[-1], slow_sma[-2]

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Golden Cross
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=0.80,
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.trending_bullish,
                        supporting_indicators={
                            "fast_sma": curr_fast,
                            "slow_sma": curr_slow,
                        },
                        explanation=f"Golden Cross: Fast SMA ({curr_fast:.2f}) crossed above Slow SMA ({curr_slow:.2f}).",
                    )
                )

        # Death Cross
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.80,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.trending_bearish,
                        supporting_indicators={
                            "fast_sma": curr_fast,
                            "slow_sma": curr_slow,
                        },
                        explanation=f"Death Cross: Fast SMA ({curr_fast:.2f}) crossed below Slow SMA ({curr_slow:.2f}).",
                    )
                )

        return signals
