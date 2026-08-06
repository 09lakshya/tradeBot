"""Donchian Channel Breakout Strategy."""
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
from app.domains.strategies.indicators import donchian_channels
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class DonchianBreakoutStrategy(BaseStrategy):
    """Donchian Channel (N-bar High / N-bar Low) Turtle Breakout Strategy."""

    strategy_id: str = "donchian_breakout"
    strategy_name: str = "Donchian Channel Breakout Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Enters on 20-bar channel high breakout with trailing exit on 10-bar channel low breakdown."
    category: StrategyCategory = StrategyCategory.momentum
    required_lookback: int = 30

    default_parameters: dict[str, Any] = {
        "entry_period": 20,
        "exit_period": 10,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0250",
        "take_profit_pct": "0.0600",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        entry_p = int(self.params["entry_period"])
        history = context.get_history(bar.instrument_id, lookback_bars=entry_p + 5)
        if len(history) < entry_p + 1:
            return []

        highs = [float(b.high) for b in history]
        lows = [float(b.low) for b in history]

        # Prior N-bar high/low (excluding current bar)
        prior_highs = highs[:-1]
        prior_lows = lows[:-1]

        upper_entry, _, _ = donchian_channels(prior_highs, prior_lows, entry_p)
        _, _, lower_exit = donchian_channels(prior_highs, prior_lows, int(self.params["exit_period"]))

        breakout_level = upper_entry[-1]
        exit_level = lower_exit[-1]

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Breakout Above Entry High
        if float(bar.close) > breakout_level:
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
                            "channel_high_20": breakout_level,
                            "channel_low_10": exit_level,
                        },
                        explanation=f"Donchian Breakout: Close ({float(bar.close):.2f}) broke above {entry_p}-bar high ({breakout_level:.2f}).",
                    )
                )

        # Breakdown Below Exit Low
        elif float(bar.close) < exit_level:
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
                            "channel_low_10": exit_level,
                        },
                        explanation=f"Donchian Exit Breakdown: Close ({float(bar.close):.2f}) fell below {self.params['exit_period']}-bar low ({exit_level:.2f}).",
                    )
                )

        return signals
