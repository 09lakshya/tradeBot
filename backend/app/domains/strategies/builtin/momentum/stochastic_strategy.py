"""Stochastic Oscillator Momentum Strategy."""
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
from app.domains.strategies.indicators import stochastic
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class StochasticStrategy(BaseStrategy):
    """Stochastic Oscillator (%K and %D) Crossover Strategy in Extreme Zones."""

    strategy_id: str = "stochastic_momentum"
    strategy_name: str = "Stochastic Crossover Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Enters long when %K crosses above %D in the oversold zone (<20) and exits on %K crossing below %D in overbought (>80)."
    category: StrategyCategory = StrategyCategory.momentum
    required_lookback: int = 30

    default_parameters: dict[str, Any] = {
        "k_period": 14,
        "d_period": 3,
        "smooth_k": 3,
        "oversold_threshold": 20.0,
        "overbought_threshold": 80.0,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",
        "take_profit_pct": "0.0400",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        k_p = int(self.params["k_period"])
        history = context.get_history(bar.instrument_id, lookback_bars=k_p + 15)
        if len(history) < k_p + 6:
            return []

        highs = [float(b.high) for b in history]
        lows = [float(b.low) for b in history]
        closes = [float(b.close) for b in history]

        k_line, d_line = stochastic(
            highs,
            lows,
            closes,
            k_period=k_p,
            d_period=int(self.params["d_period"]),
            smooth_k=int(self.params["smooth_k"]),
        )

        curr_k, prev_k = k_line[-1], k_line[-2]
        curr_d, prev_d = d_line[-1], d_line[-2]
        oversold = float(self.params["oversold_threshold"])
        overbought = float(self.params["overbought_threshold"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Bullish Stochastic Cross in Oversold Zone
        if prev_k <= prev_d and curr_k > curr_d and prev_k <= oversold:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=0.82,
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.ranging,
                        supporting_indicators={
                            "percent_k": curr_k,
                            "percent_d": curr_d,
                            "oversold_threshold": oversold,
                        },
                        explanation=f"Bullish Stochastic Cross: %K ({curr_k:.1f}) crossed above %D ({curr_d:.1f}) in oversold zone (<= {oversold}).",
                    )
                )

        # Bearish Stochastic Cross in Overbought Zone
        elif prev_k >= prev_d and curr_k < curr_d and curr_k >= (overbought - 10.0):
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.80,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.ranging,
                        supporting_indicators={
                            "percent_k": curr_k,
                            "percent_d": curr_d,
                            "overbought_threshold": overbought,
                        },
                        explanation=f"Bearish Stochastic Cross: %K ({curr_k:.1f}) crossed below %D ({curr_d:.1f}) near overbought zone.",
                    )
                )

        return signals
