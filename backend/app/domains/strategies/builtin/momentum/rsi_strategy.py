"""RSI Momentum and Mean Reversion Strategy."""
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
from app.domains.strategies.indicators import rsi
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class RSIStrategy(BaseStrategy):
    """Relative Strength Index (RSI) Oversold / Overbought Dynamic Strategy."""

    strategy_id: str = "rsi_momentum"
    strategy_name: str = "RSI Momentum & Reversal Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Enters long when RSI recovers from oversold conditions (<30) and exits when reaching overbought (>70)."
    category: StrategyCategory = StrategyCategory.momentum
    required_lookback: int = 40

    default_parameters: dict[str, Any] = {
        "period": 14,
        "oversold_threshold": 30.0,
        "overbought_threshold": 70.0,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",
        "take_profit_pct": "0.0400",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        period = int(self.params["period"])
        history = context.get_history(bar.instrument_id, lookback_bars=period + 10)
        if len(history) < period + 2:
            return []

        closes = [float(b.close) for b in history]
        rsi_vals = rsi(closes, period)

        curr_rsi, prev_rsi = rsi_vals[-1], rsi_vals[-2]
        oversold = float(self.params["oversold_threshold"])
        overbought = float(self.params["overbought_threshold"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Oversold Rebound: RSI was <= oversold and crosses above oversold
        if prev_rsi <= oversold and curr_rsi > oversold:
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
                        market_regime=MarketRegime.ranging,
                        supporting_indicators={
                            "rsi": curr_rsi,
                            "prev_rsi": prev_rsi,
                            "oversold_threshold": oversold,
                        },
                        explanation=f"RSI Rebound from Oversold: RSI ({curr_rsi:.1f}) crossed above {oversold}.",
                    )
                )

        # Overbought Exit: RSI reaches or exceeds overbought threshold
        elif curr_rsi >= overbought:
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.85,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.ranging,
                        supporting_indicators={
                            "rsi": curr_rsi,
                            "overbought_threshold": overbought,
                        },
                        explanation=f"RSI Overbought Target: RSI ({curr_rsi:.1f}) reached overbought threshold {overbought}.",
                    )
                )

        return signals
