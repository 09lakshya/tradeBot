"""ATR Volatility Expansion Breakout Strategy."""
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
from app.domains.strategies.indicators import atr, sma
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class ATRBreakoutStrategy(BaseStrategy):
    """ATR Volatility Expansion Breakout Strategy."""

    strategy_id: str = "atr_breakout"
    strategy_name: str = "ATR Volatility Expansion Breakout"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Detects volatility compression followed by sudden range expansion exceeding N * ATR."
    category: StrategyCategory = StrategyCategory.volatility
    required_lookback: int = 30

    default_parameters: dict[str, Any] = {
        "atr_period": 14,
        "sma_period": 20,
        "atr_multiplier": 2.0,
        "trade_qty": "10.0000",
        "trailing_atr_multiplier": 1.5,
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        lookback = max(int(self.params["atr_period"]), int(self.params["sma_period"])) + 5
        history = context.get_history(bar.instrument_id, lookback_bars=lookback)
        if len(history) < max(int(self.params["atr_period"]), int(self.params["sma_period"])):
            return []

        highs = [float(b.high) for b in history]
        lows = [float(b.low) for b in history]
        closes = [float(b.close) for b in history]

        atr_vals = atr(highs, lows, closes, int(self.params["atr_period"]))
        baseline_sma = sma(closes, int(self.params["sma_period"]))

        curr_atr = atr_vals[-1]
        curr_sma = baseline_sma[-1]
        mult = float(self.params["atr_multiplier"])
        breakout_barrier = curr_sma + mult * curr_atr

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))

        # Volatility Breakout Entry: Close > SMA + Mult * ATR
        if float(bar.close) > breakout_barrier:
            if curr_pos <= Decimal("0.0000"):
                sl_dist = Decimal(str(f"{curr_atr * float(self.params['trailing_atr_multiplier']):.2f}"))
                sl = (bar.close - sl_dist).quantize(Decimal("0.01"))
                tp = (bar.close + sl_dist * Decimal("2.0")).quantize(Decimal("0.01"))
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
                        market_regime=MarketRegime.volatile_expansion,
                        supporting_indicators={
                            "atr": curr_atr,
                            "baseline_sma": curr_sma,
                            "breakout_barrier": breakout_barrier,
                        },
                        explanation=f"ATR Volatility Breakout: Close ({float(bar.close):.2f}) surged above baseline SMA + {mult}x ATR ({breakout_barrier:.2f}).",
                    )
                )

        # Reversion Below Baseline Exit
        elif float(bar.close) < curr_sma:
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
                            "baseline_sma": curr_sma,
                        },
                        explanation=f"ATR Strategy Exit: Price fell back below baseline SMA ({curr_sma:.2f}).",
                    )
                )

        return signals
