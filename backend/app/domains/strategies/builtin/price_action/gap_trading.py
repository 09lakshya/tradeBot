"""Opening Gap Trading Strategy (Gap Fade & Gap Fill)."""
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
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class GapTradingStrategy(BaseStrategy):
    """Opening Gap-Down Fade Strategy (Buys oversold gap-downs for morning gap fill)."""

    strategy_id: str = "gap_trading"
    strategy_name: str = "Opening Gap Fade Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Identifies opening gap-downs between 0.5% and 2.5% and trades mean-reversion toward previous close."
    category: StrategyCategory = StrategyCategory.price_action
    required_lookback: int = 10

    default_parameters: dict[str, Any] = {
        "min_gap_pct": "0.0050",  # 0.5%
        "max_gap_pct": "0.0250",  # 2.5%
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0150",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        history = context.get_history(bar.instrument_id, lookback_bars=5)
        if len(history) < 2:
            return []

        prev_bar = history[-2]
        prev_close = float(prev_bar.close)
        curr_open = float(bar.open)
        curr_close = float(bar.close)

        gap_pct = (curr_open - prev_close) / prev_close
        min_gap = float(self.params["min_gap_pct"])
        max_gap = float(self.params["max_gap_pct"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))

        # Gap Down within range: -max_gap <= gap_pct <= -min_gap AND bar shows buying (close > open)
        if -max_gap <= gap_pct <= -min_gap and curr_close > curr_open:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = Decimal(str(f"{prev_close:.2f}"))
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
                            "gap_pct": gap_pct * 100.0,
                            "previous_close": prev_close,
                            "open_price": curr_open,
                        },
                        explanation=f"Gap-Down Fade: Opening gap of {gap_pct*100.0:.2f}% with bullish reversal bar. Target is Gap Fill ({prev_close:.2f}).",
                    )
                )

        # Gap Filled Exit: Close >= Previous Close
        elif curr_close >= prev_close:
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
                            "previous_close": prev_close,
                        },
                        explanation=f"Gap Fill Exit: Price filled previous session close ({prev_close:.2f}).",
                    )
                )

        return signals
