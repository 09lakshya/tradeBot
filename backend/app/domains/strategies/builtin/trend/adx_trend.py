"""ADX Trend Following Strategy."""
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
from app.domains.strategies.indicators import adx
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class ADXTrendStrategy(BaseStrategy):
    """Average Directional Index (ADX) Trend Strength and Direction (+DI / -DI) Strategy."""

    strategy_id: str = "adx_trend"
    strategy_name: str = "ADX Trend Strength Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Identifies strong trends when ADX > threshold and enters in the direction of +DI/-DI."
    category: StrategyCategory = StrategyCategory.trend_following
    required_lookback: int = 50

    default_parameters: dict[str, Any] = {
        "period": 14,
        "adx_threshold": 25.0,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",
        "take_profit_pct": "0.0500",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        period = int(self.params["period"])
        history = context.get_history(bar.instrument_id, lookback_bars=period * 3)
        if len(history) < period * 2 + 5:
            return []

        highs = [float(b.high) for b in history]
        lows = [float(b.low) for b in history]
        closes = [float(b.close) for b in history]

        plus_di, minus_di, adx_vals = adx(highs, lows, closes, period)
        curr_p_di, prev_p_di = plus_di[-1], plus_di[-2]
        curr_m_di, prev_m_di = minus_di[-1], minus_di[-2]
        curr_adx = adx_vals[-1]

        thresh = float(self.params["adx_threshold"])
        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Bullish Strong Trend: ADX > threshold AND +DI crosses above -DI
        if curr_adx >= thresh and prev_p_di <= prev_m_di and curr_p_di > curr_m_di:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=min(1.0, 0.70 + (curr_adx / 100.0) * 0.30),
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.trending_bullish,
                        supporting_indicators={
                            "adx": curr_adx,
                            "plus_di": curr_p_di,
                            "minus_di": curr_m_di,
                        },
                        explanation=f"Strong Bullish Trend: ADX ({curr_adx:.1f} >= {thresh}) with +DI ({curr_p_di:.1f}) crossing above -DI ({curr_m_di:.1f}).",
                    )
                )

        # Bearish / Trend Exhaustion Exit
        elif curr_p_di < curr_m_di or curr_adx < (thresh - 5.0):
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.75,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.ranging if curr_adx < thresh else MarketRegime.trending_bearish,
                        supporting_indicators={
                            "adx": curr_adx,
                            "plus_di": curr_p_di,
                            "minus_di": curr_m_di,
                        },
                        explanation=f"Trend Exhaustion Exit: +DI fell below -DI or ADX ({curr_adx:.1f}) softened.",
                    )
                )

        return signals
