"""Opening Range Breakout (ORB) Strategy."""
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
class OpeningRangeBreakoutStrategy(BaseStrategy):
    """Institutional Opening Range Breakout (ORB 15/30-min Range Breakout)."""

    strategy_id: str = "opening_range_breakout"
    strategy_name: str = "Opening Range Breakout (ORB)"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Establishes the session high/low over the first N bars and executes on upside breakout with volume confirmation."
    category: StrategyCategory = StrategyCategory.institutional
    required_lookback: int = 15

    default_parameters: dict[str, Any] = {
        "range_bars": 3,  # First 3 bars (e.g. 15-min or 45-min range)
        "volume_threshold_ratio": 1.2,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0150",
        "take_profit_pct": "0.0350",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        r_bars = int(self.params["range_bars"])
        history = context.get_history(bar.instrument_id, lookback_bars=r_bars + 5)
        if len(history) < r_bars + 1:
            return []

        orb_bars = history[:r_bars]
        orb_high = max(float(b.high) for b in orb_bars)
        orb_low = min(float(b.low) for b in orb_bars)
        orb_avg_vol = sum(float(b.volume) for b in orb_bars) / r_bars

        curr_close = float(bar.close)
        curr_vol = float(bar.volume)
        vol_ratio = curr_vol / orb_avg_vol if orb_avg_vol > 0 else 1.0

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # ORB Upside Breakout
        if curr_close > orb_high and vol_ratio >= float(self.params["volume_threshold_ratio"]):
            if curr_pos <= Decimal("0.0000"):
                sl = Decimal(str(f"{orb_low:.2f}"))
                # If ORB low is too far, clamp with stop_loss_pct
                max_sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                if sl < max_sl:
                    sl = max_sl
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))

                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=0.88,
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.volatile_expansion,
                        supporting_indicators={
                            "orb_high": orb_high,
                            "orb_low": orb_low,
                            "volume_ratio": vol_ratio,
                        },
                        explanation=f"ORB Breakout: Close ({curr_close:.2f}) broke above {r_bars}-bar opening range high ({orb_high:.2f}) with {vol_ratio:.1f}x volume.",
                    )
                )

        # Breakdown Below Opening Range Low Exit
        elif curr_close < orb_low:
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.85,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.trending_bearish,
                        supporting_indicators={
                            "orb_low": orb_low,
                        },
                        explanation=f"ORB Range Failure: Price ({curr_close:.2f}) breached opening range low ({orb_low:.2f}).",
                    )
                )

        return signals
