"""VWAP Mean Reversion Strategy."""
from decimal import Decimal
import math
from typing import Any

from app.domains.backtest.data_feed import HistoricalBar
from app.domains.strategies.base import BaseStrategy, StrategyContext
from app.domains.strategies.enums import (
    MarketRegime,
    SignalDirection,
    SignalType,
    StrategyCategory,
)
from app.domains.strategies.indicators import vwap
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class VWAPReversionStrategy(BaseStrategy):
    """Intraday VWAP Standard Deviation Band Reversion Strategy."""

    strategy_id: str = "vwap_reversion"
    strategy_name: str = "VWAP Deviation Mean Reversion"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Trades price deviations beyond 2.0 standard deviations from intraday VWAP back towards VWAP equilibrium."
    category: StrategyCategory = StrategyCategory.mean_reversion
    required_lookback: int = 40

    default_parameters: dict[str, Any] = {
        "lookback_bars": 30,
        "deviation_threshold": 2.0,  # 2.0 standard deviations from VWAP
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0150",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        lookback = int(self.params["lookback_bars"])
        history = context.get_history(bar.instrument_id, lookback_bars=lookback)
        if len(history) < lookback:
            return []

        highs = [float(b.high) for b in history]
        lows = [float(b.low) for b in history]
        closes = [float(b.close) for b in history]
        volumes = [float(b.volume) for b in history]

        vwap_vals = vwap(highs, lows, closes, volumes)
        curr_vwap = vwap_vals[-1]
        curr_close = closes[-1]

        # Calculate standard deviation around VWAP
        deviations = [c - v for c, v in zip(closes, vwap_vals)]
        mean_dev = sum(deviations) / len(deviations)
        variance = sum((d - mean_dev) ** 2 for d in deviations) / len(deviations)
        std_dev = math.sqrt(variance) if variance > 0 else 1.0

        curr_z = (curr_close - curr_vwap) / std_dev
        thresh = float(self.params["deviation_threshold"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))

        # Oversold below VWAP: Z-Score <= -thresh
        if curr_z <= -thresh:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = Decimal(str(f"{curr_vwap:.2f}"))
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
                            "vwap": curr_vwap,
                            "vwap_zscore": curr_z,
                            "std_dev": std_dev,
                        },
                        explanation=f"VWAP Oversold Reversion: Price ({curr_close:.2f}) is {curr_z:.2f} standard deviations below VWAP ({curr_vwap:.2f}).",
                    )
                )

        # Reverted back to VWAP
        elif curr_close >= curr_vwap:
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
                            "vwap": curr_vwap,
                            "vwap_zscore": curr_z,
                        },
                        explanation=f"VWAP Reversion Exit: Price ({curr_close:.2f}) reached VWAP benchmark ({curr_vwap:.2f}).",
                    )
                )

        return signals
