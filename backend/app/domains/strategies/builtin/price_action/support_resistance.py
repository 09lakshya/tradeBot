"""Support & Resistance Pivot Level Bounce/Breakout Strategy."""
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
from app.domains.strategies.indicators import pivot_points_standard
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class SupportResistancePivotStrategy(BaseStrategy):
    """Support & Resistance Standard Floor Pivot Points Bounce Strategy."""

    strategy_id: str = "support_resistance"
    strategy_name: str = "Support & Resistance Pivot Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Buys when price bounces off S1/S2 support levels with target at the central Pivot P."
    category: StrategyCategory = StrategyCategory.price_action
    required_lookback: int = 20

    default_parameters: dict[str, Any] = {
        "trade_qty": "10.0000",
        "tolerance_pct": "0.0050",  # 0.5% buffer near pivot levels
        "stop_loss_pct": "0.0150",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        history = context.get_history(bar.instrument_id, lookback_bars=10)
        if len(history) < 2:
            return []

        # Use previous day / previous bar session high/low/close for pivots
        prev_bar = history[-2]
        pivots = pivot_points_standard(
            float(prev_bar.high),
            float(prev_bar.low),
            float(prev_bar.close),
        )

        curr_close = float(bar.close)
        s1 = pivots["S1"]
        p_val = pivots["P"]
        r1 = pivots["R1"]
        tol = float(self.params["tolerance_pct"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))

        # S1 Support Bounce: Price touched near S1 and closed bullish
        if abs(curr_close - s1) / s1 <= tol and float(bar.close) > float(bar.open):
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = Decimal(str(f"{p_val:.2f}"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=0.83,
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.ranging,
                        supporting_indicators=pivots,
                        explanation=f"Support Bounce: Price ({curr_close:.2f}) bounced off S1 Support ({s1:.2f}) with target at Central Pivot ({p_val:.2f}).",
                    )
                )

        # Central Pivot Target Reached Exit
        elif curr_close >= p_val:
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
                        supporting_indicators=pivots,
                        explanation=f"Pivot Target Reached: Price ({curr_close:.2f}) attained central pivot ({p_val:.2f}).",
                    )
                )

        return signals
