"""Statistical Z-Score Mean Reversion Strategy."""
import math
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
class ZScoreMeanReversionStrategy(BaseStrategy):
    """Statistical Rolling Price Z-Score Mean Reversion Strategy."""

    strategy_id: str = "zscore_reversion"
    strategy_name: str = "Price Z-Score Mean Reversion"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Buys statistical extreme deviations (Z-score <= -2.0) and exits when Z-score crosses above 0."
    category: StrategyCategory = StrategyCategory.mean_reversion
    required_lookback: int = 35

    default_parameters: dict[str, Any] = {
        "period": 20,
        "entry_z": -2.0,
        "exit_z": 0.0,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        period = int(self.params["period"])
        history = context.get_history(bar.instrument_id, lookback_bars=period + 5)
        if len(history) < period:
            return []

        closes = [float(b.close) for b in history][-period:]
        mean_p = sum(closes) / period
        variance = sum((c - mean_p) ** 2 for c in closes) / period
        std_p = math.sqrt(variance) if variance > 0 else 1.0

        curr_z = (closes[-1] - mean_p) / std_p
        entry_z = float(self.params["entry_z"])
        exit_z = float(self.params["exit_z"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))

        # Extreme Negative Z-Score Entry
        if curr_z <= entry_z:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = Decimal(str(f"{mean_p:.2f}"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=min(1.0, 0.70 + (abs(curr_z) / 4.0) * 0.30),
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.ranging,
                        supporting_indicators={
                            "z_score": curr_z,
                            "rolling_mean": mean_p,
                            "rolling_std": std_p,
                        },
                        explanation=f"Z-Score Mean Reversion Entry: Price Z-Score ({curr_z:.2f}) reached extreme negative threshold (<= {entry_z:.2f}).",
                    )
                )

        # Reverted back to Mean
        elif curr_z >= exit_z:
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
                            "z_score": curr_z,
                            "rolling_mean": mean_p,
                        },
                        explanation=f"Z-Score Mean Reversion Exit: Price Z-Score ({curr_z:.2f}) returned above mean ({exit_z:.2f}).",
                    )
                )

        return signals
