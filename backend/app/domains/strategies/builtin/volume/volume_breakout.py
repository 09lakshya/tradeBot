"""Volume Surge and Price Expansion Breakout Strategy."""
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
class VolumeBreakoutStrategy(BaseStrategy):
    """Institutional Volume Surge with Strong Directional Candle Breakout."""

    strategy_id: str = "volume_breakout"
    strategy_name: str = "Volume Surge Breakout Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Detects institutional accumulation when Volume > 2.0x 20-day Average Volume with a bullish candle."
    category: StrategyCategory = StrategyCategory.volume
    required_lookback: int = 30

    default_parameters: dict[str, Any] = {
        "volume_ma_period": 20,
        "volume_multiplier": 2.0,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",
        "take_profit_pct": "0.0500",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        ma_p = int(self.params["volume_ma_period"])
        history = context.get_history(bar.instrument_id, lookback_bars=ma_p + 5)
        if len(history) < ma_p:
            return []

        volumes = [float(b.volume) for b in history]
        vol_sma = sma(volumes, ma_p)

        curr_vol = volumes[-1]
        avg_vol = vol_sma[-1]
        mult = float(self.params["volume_multiplier"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        is_bullish_candle = float(bar.close) > float(bar.open)

        # Volume Surge with Bullish Close
        if curr_vol >= mult * avg_vol and is_bullish_candle:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=min(1.0, 0.75 + (curr_vol / (mult * avg_vol) - 1.0) * 0.20),
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.volatile_expansion,
                        supporting_indicators={
                            "current_volume": curr_vol,
                            "average_volume": avg_vol,
                            "volume_ratio": curr_vol / avg_vol if avg_vol > 0 else 1.0,
                        },
                        explanation=f"Volume Surge Breakout: Volume ({curr_vol:.0f}) surged to {curr_vol/avg_vol:.1f}x 20-bar average ({avg_vol:.0f}) with bullish candle.",
                    )
                )

        # Exit on volume collapse below 0.5x average on red candle
        elif curr_vol < 0.5 * avg_vol and float(bar.close) < float(bar.open):
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.75,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.ranging,
                        supporting_indicators={
                            "current_volume": curr_vol,
                            "average_volume": avg_vol,
                        },
                        explanation="Volume Exhaustion Exit: Low volume red candle indicates buying exhaustion.",
                    )
                )

        return signals
