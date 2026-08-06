"""MACD Trend Strategy."""
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
from app.domains.strategies.indicators import macd
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class MACDTrendStrategy(BaseStrategy):
    """MACD Line and Signal Crossover with Zero-Line Momentum Filter."""

    strategy_id: str = "macd_trend"
    strategy_name: str = "MACD Trend Momentum Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Trades MACD line and signal line crossovers with histogram confirmation."
    category: StrategyCategory = StrategyCategory.trend_following
    required_lookback: int = 60

    default_parameters: dict[str, Any] = {
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0250",
        "take_profit_pct": "0.0500",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        slow_p = int(self.params["slow_period"])
        history = context.get_history(bar.instrument_id, lookback_bars=slow_p + 30)
        if len(history) < slow_p + 15:
            return []

        closes = [float(b.close) for b in history]
        macd_line, sig_line, hist = macd(
            closes,
            fast_period=int(self.params["fast_period"]),
            slow_period=slow_p,
            signal_period=int(self.params["signal_period"]),
        )

        curr_m, prev_m = macd_line[-1], macd_line[-2]
        curr_s, prev_s = sig_line[-1], sig_line[-2]
        curr_h = hist[-1]

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Bullish Crossover: MACD line crosses above Signal line
        if prev_m <= prev_s and curr_m > curr_s and curr_h > 0:
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
                        market_regime=MarketRegime.trending_bullish,
                        supporting_indicators={
                            "macd_line": curr_m,
                            "signal_line": curr_s,
                            "histogram": curr_h,
                        },
                        explanation=f"Bullish MACD Cross: MACD Line ({curr_m:.2f}) crossed above Signal ({curr_s:.2f}) with positive histogram ({curr_h:.2f}).",
                    )
                )

        # Bearish Crossover: MACD line crosses below Signal line
        elif prev_m >= prev_s and curr_m < curr_s:
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
                            "macd_line": curr_m,
                            "signal_line": curr_s,
                            "histogram": curr_h,
                        },
                        explanation=f"Bearish MACD Cross: MACD Line ({curr_m:.2f}) crossed below Signal ({curr_s:.2f}).",
                    )
                )

        return signals
