"""EMA Crossover Trend Following Strategy."""
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
from app.domains.strategies.indicators import ema
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class EMACrossoverStrategy(BaseStrategy):
    """Dual Exponential Moving Average (Fast EMA x Slow EMA) with 200 EMA baseline trend filter."""

    strategy_id: str = "ema_crossover"
    strategy_name: str = "EMA Crossover Trend Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Generates trend-following signals on Fast EMA / Slow EMA crosses filtered by baseline trend."
    category: StrategyCategory = StrategyCategory.trend_following
    required_lookback: int = 210

    default_parameters: dict[str, Any] = {
        "fast_period": 9,
        "slow_period": 21,
        "trend_filter_period": 200,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",  # 2% stop loss
        "take_profit_pct": "0.0400",  # 4% profit target
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        lookback = int(self.params["trend_filter_period"]) + 10
        history = context.get_history(bar.instrument_id, lookback_bars=lookback)
        if len(history) < int(self.params["trend_filter_period"]):
            return []

        closes = [float(b.close) for b in history]
        fast_p = int(self.params["fast_period"])
        slow_p = int(self.params["slow_period"])
        filter_p = int(self.params["trend_filter_period"])

        fast_ema = ema(closes, fast_p)
        slow_ema = ema(closes, slow_p)
        trend_ema = ema(closes, filter_p)

        curr_fast, prev_fast = fast_ema[-1], fast_ema[-2]
        curr_slow, prev_slow = slow_ema[-1], slow_ema[-2]
        curr_trend = trend_ema[-1]

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Bullish Crossover: Fast crosses above Slow AND Price is above 200 EMA
        if prev_fast <= prev_slow and curr_fast > curr_slow and closes[-1] >= curr_trend:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=0.85,
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.trending_bullish,
                        supporting_indicators={
                            "fast_ema": curr_fast,
                            "slow_ema": curr_slow,
                            "trend_ema": curr_trend,
                            "close": closes[-1],
                        },
                        explanation=f"Bullish EMA Crossover: Fast EMA ({curr_fast:.2f}) crossed above Slow EMA ({curr_slow:.2f}) above 200 EMA ({curr_trend:.2f}).",
                    )
                )

        # Bearish Cross / Exit Long: Fast crosses below Slow
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
                            "fast_ema": curr_fast,
                            "slow_ema": curr_slow,
                            "trend_ema": curr_trend,
                        },
                        explanation=f"Bearish EMA Cross: Fast EMA ({curr_fast:.2f}) crossed below Slow EMA ({curr_slow:.2f}).",
                    )
                )

        return signals
