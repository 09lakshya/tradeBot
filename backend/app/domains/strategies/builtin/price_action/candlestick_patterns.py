"""Candlestick Pattern Recognition Strategy."""
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
from app.domains.strategies.indicators import candlestick_patterns, ema
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class CandlestickPatternStrategy(BaseStrategy):
    """Multi-Pattern Candlestick Price Action Strategy (Hammer, Bullish Engulfing, Morning Star)."""

    strategy_id: str = "candlestick_patterns"
    strategy_name: str = "Candlestick Pattern Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Enters long on high-probability bullish reversal patterns (Hammer, Engulfing, Morning Star) aligned with 50 EMA."
    category: StrategyCategory = StrategyCategory.price_action
    required_lookback: int = 55

    default_parameters: dict[str, Any] = {
        "trend_ema_period": 50,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",
        "take_profit_pct": "0.0450",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        history = context.get_history(bar.instrument_id, lookback_bars=60)
        if len(history) < 52:
            return []

        opens = [float(b.open) for b in history]
        highs = [float(b.high) for b in history]
        lows = [float(b.low) for b in history]
        closes = [float(b.close) for b in history]

        patterns = candlestick_patterns(opens, highs, lows, closes)
        trend_emas = ema(closes, int(self.params["trend_ema_period"]))

        is_hammer = patterns["hammer"][-1]
        is_bull_engulf = patterns["bullish_engulfing"][-1]
        is_morning_star = patterns["morning_star"][-1]
        is_bear_engulf = patterns["bearish_engulfing"][-1]
        is_shooting_star = patterns["shooting_star"][-1]

        curr_close = closes[-1]
        curr_ema = trend_emas[-1]

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Bullish Reversal Pattern above/near 50 EMA
        if (is_hammer or is_bull_engulf or is_morning_star) and curr_close >= (curr_ema * 0.98):
            if curr_pos <= Decimal("0.0000"):
                pattern_name = "Morning Star" if is_morning_star else ("Bullish Engulfing" if is_bull_engulf else "Hammer")
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
                            "pattern": pattern_name,
                            "trend_ema": curr_ema,
                        },
                        explanation=f"Bullish Price Action Pattern: {pattern_name} formed near {self.params['trend_ema_period']} EMA ({curr_ema:.2f}).",
                    )
                )

        # Bearish Reversal Pattern Exit
        elif is_bear_engulf or is_shooting_star:
            if curr_pos > Decimal("0.0000"):
                pattern_name = "Bearish Engulfing" if is_bear_engulf else "Shooting Star"
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
                            "pattern": pattern_name,
                        },
                        explanation=f"Bearish Pattern Exit: {pattern_name} detected.",
                    )
                )

        return signals
