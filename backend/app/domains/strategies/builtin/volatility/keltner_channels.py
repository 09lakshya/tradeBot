"""Keltner Channel Squeeze & Breakout Strategy."""
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
from app.domains.strategies.indicators import keltner_channels
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class KeltnerChannelStrategy(BaseStrategy):
    """Keltner Channel Squeeze and Volatility Expansion Strategy."""

    strategy_id: str = "keltner_channel"
    strategy_name: str = "Keltner Channel Squeeze Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Trades Bollinger inside Keltner volatility squeeze breakouts."
    category: StrategyCategory = StrategyCategory.volatility
    required_lookback: int = 35

    default_parameters: dict[str, Any] = {
        "ema_period": 20,
        "atr_period": 10,
        "multiplier": 2.0,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",
        "take_profit_pct": "0.0500",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        lookback = max(int(self.params["ema_period"]), int(self.params["atr_period"])) + 10
        history = context.get_history(bar.instrument_id, lookback_bars=lookback)
        if len(history) < max(int(self.params["ema_period"]), int(self.params["atr_period"])) + 2:
            return []

        highs = [float(b.high) for b in history]
        lows = [float(b.low) for b in history]
        closes = [float(b.close) for b in history]

        k_upper, k_mid, k_lower = keltner_channels(
            highs,
            lows,
            closes,
            ema_period=int(self.params["ema_period"]),
            atr_period=int(self.params["atr_period"]),
            multiplier=float(self.params["multiplier"]),
        )

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        curr_close = closes[-1]
        prev_close = closes[-2]
        curr_ku = k_upper[-1]
        prev_ku = k_upper[-2]
        curr_mid = k_mid[-1]

        # Breakout Above Upper Keltner Channel
        if prev_close <= prev_ku and curr_close > curr_ku:
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
                        market_regime=MarketRegime.volatile_expansion,
                        supporting_indicators={
                            "keltner_upper": curr_ku,
                            "keltner_middle": curr_mid,
                        },
                        explanation=f"Keltner Breakout: Price ({curr_close:.2f}) broke above Upper Keltner Channel ({curr_ku:.2f}).",
                    )
                )

        # Fall Below Middle EMA Exit
        elif curr_close < curr_mid:
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
                            "keltner_middle": curr_mid,
                        },
                        explanation=f"Keltner Exit: Price fell below middle EMA ({curr_mid:.2f}).",
                    )
                )

        return signals
