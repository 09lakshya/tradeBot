"""Bollinger Bands Mean Reversion Strategy."""
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
from app.domains.strategies.indicators import bollinger_bands
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class BollingerBandsStrategy(BaseStrategy):
    """Bollinger Bands Mean Reversion Strategy (Lower Band Bounce to Middle SMA)."""

    strategy_id: str = "bollinger_mean_reversion"
    strategy_name: str = "Bollinger Bands Mean Reversion"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Buys when price touches or dips below the lower Bollinger Band and takes profit at the middle SMA."
    category: StrategyCategory = StrategyCategory.mean_reversion
    required_lookback: int = 30

    default_parameters: dict[str, Any] = {
        "period": 20,
        "num_std": 2.0,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        period = int(self.params["period"])
        history = context.get_history(bar.instrument_id, lookback_bars=period + 5)
        if len(history) < period:
            return []

        closes = [float(b.close) for b in history]
        upper, middle, lower, pct_b, bandwidth = bollinger_bands(
            closes,
            period=period,
            num_std=float(self.params["num_std"]),
        )

        curr_close = closes[-1]
        curr_upper = upper[-1]
        curr_middle = middle[-1]
        curr_lower = lower[-1]
        curr_pct_b = pct_b[-1]

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))

        # Oversold Mean Reversion Entry: Close <= Lower Band or %B <= 0.05
        if curr_pct_b <= 0.05 or curr_close <= curr_lower:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = Decimal(str(f"{curr_middle:.2f}"))
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
                            "lower_band": curr_lower,
                            "middle_band": curr_middle,
                            "upper_band": curr_upper,
                            "percent_b": curr_pct_b,
                        },
                        explanation=f"Bollinger Oversold Reversion: Price ({curr_close:.2f}) touched lower band ({curr_lower:.2f}) with %B={curr_pct_b:.2f}.",
                    )
                )

        # Mean Reversion Target Achieved: Close >= Middle Band
        elif curr_close >= curr_middle:
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
                            "middle_band": curr_middle,
                            "percent_b": curr_pct_b,
                        },
                        explanation=f"Bollinger Mean Reversion Target Reached: Price ({curr_close:.2f}) reached middle band ({curr_middle:.2f}).",
                    )
                )

        return signals
